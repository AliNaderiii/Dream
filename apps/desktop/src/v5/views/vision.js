/**
 * Vision — one real action: capture the screen and extract its Persian text.
 * `vision.capture_screen` (Windows GDI) writes a temp file, OCRs it with the
 * core engine, and deletes the file immediately — screen pixels never
 * persist (P-14). Privacy note is surfaced in the UI, not buried.
 */

import { h, fmtBytes } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, pickFolder, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

export function visionView(root, ctx) {
  let result = null; // capture_screen OCR result
  let diagramResult = null; // inspect_diagram structural result
  let capabilities = null;
  let contract = null;
  let imageResult = null;
  let imageAnalysis = null;
  let roots = [];
  let pdfResult = null;
  let pdfEvidence = null; // shown on demand — the drawer never opens itself
  let busy = '';
  let error = null;

  const stage = h('div', { class: 'vision-stage' });
  const diagramStage = h('div', { class: 'vision-diagram-stage' });
  const readinessStage = h('div', { class: 'vision-readiness-stage' });
  const imageStage = h('div', { class: 'vision-image-stage' });
  const imageRoot = h('select', { class: 'input', 'aria-label': 'ریشهٔ تصویر' });
  const imagePath = h('input', {
    class: 'input mono',
    dir: 'ltr',
    placeholder: 'مسیر نسبی تصویر در ریشه، مثلاً assets/photo.png',
  });
  const imagePrompt = h('input', {
    class: 'input',
    placeholder: 'پرسش برای backend تصویری (فقط با adapter آماده)',
  });
  const diagramInput = h('textarea', {
    class: 'input vision-diagram-input',
    rows: 7,
    placeholder: 'Mermaid یا SVG را اینجا وارد کنید…',
  });
  const diagramFormat = h(
    'select',
    { class: 'input vision-diagram-format', 'aria-label': 'نوع نمودار' },
    h('option', { value: 'mermaid', text: 'Mermaid' }),
    h('option', { value: 'svg', text: 'SVG' }),
  );

  function notice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic(cls === 'ok' ? 'check' : 'alert') }, text);
  }

  function renderStage() {
    const children = [];
    if (error) children.push(notice(error));
    if (busy) children.push(h('div', { class: 'notice', html: ic('refresh') }, busy));

    if (!result && !busy) {
      children.push(
        h(
          'div',
          { class: 'voice-drop card' },
          h('span', { class: 'voice-drop-ic', html: ic('eye') }),
          h('span', { class: 'empty-title', text: 'از صفحه‌ی خود عکس بگیرید و متنش را بگیرید' }),
          h('span', {
            class: 'empty-note',
            text: 'کل صفحه فعلی گرفته می‌شود، با OCR فارسی هسته متن می‌شود و اسکرین‌شات بلافاصله و برای همیشه حذف می‌شود.',
          }),
          h(
            'span',
            { class: 'chip warn' },
            h('span', { class: 'dot' }),
            'حریم خصوصی: پیکسل‌های صفحه روی دیسک ذخیره نمی‌شوند',
          ),
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            'فقط داخل اپلیکیشن دسکتاپ — در پیش‌نمایش مرورگر صفحه‌ای برای گرفتن وجود ندارد',
          ),
        ),
      );
    }

    if (result) {
      children.push(
        h(
          'div',
          { class: 'result-panel card' },
          h('span', { class: 'micro', text: 'SCREEN TEXT' }),
          result.text
            ? h('div', { class: 'result-text', text: result.text })
            : h('span', { class: 'empty-note', text: 'متنی از صفحه استخراج نشد.' }),
          h(
            'div',
            { class: 'result-meta' },
            h(
              'span',
              { class: 'chip ok' },
              h('span', { class: 'dot' }),
              `موتور: ${result.engine || 'OCR هسته'}`,
            ),
            result.confidence != null
              ? h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `دقت: ${Math.round((result.confidence ?? 0) * 100)}%`,
                )
              : null,
            result.screen
              ? h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `صفحه ${result.screen.width ?? '—'}×${result.screen.height ?? '—'}`,
                )
              : null,
            result.text
              ? h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `${result.text.length} نویسه`,
                )
              : null,
          ),
        ),
        h(
          'div',
          { class: 'voice-actions' },
          h(
            'button',
            { class: 'btn', disabled: !!busy || !result.text, onclick: exportPdf },
            h('span', { html: ic('file') }),
            busy === 'pdf' ? 'در حال ساخت…' : 'گزارش PDF فارسی',
          ),
        ),
      );
      if (pdfResult?.success) {
        children.push(
          h(
            'div',
            { class: 'notice ok', html: ic('check') },
            `PDF ساخته شد: ${pdfResult.file_path} (${fmtBytes(pdfResult.bytes ?? 0)})`,
            pdfEvidence
              ? h(
                  'button',
                  {
                    class: 'btn btn-sm evidence-link',
                    onclick: () => ctx.openEvidence(pdfEvidence),
                  },
                  h('span', { html: ic('evidence') }),
                  'شواهد',
                )
              : null,
          ),
        );
      }
    }
    stage.replaceChildren(...children);
  }

  function renderReadiness() {
    if (!capabilities) {
      readinessStage.replaceChildren(
        h(
          'div',
          { class: 'vision-readiness card' },
          h('span', { class: 'micro', text: 'VISION READINESS' }),
          h('span', {
            class: 'muted',
            text: 'وضعیت capability از هسته خوانده می‌شود؛ هیچ شبکه‌ای برای probe استفاده نمی‌شود. inference فقط با backend واقعی فعال خواهد شد.',
          }),
        ),
      );
      return;
    }
    const rows = [
      [
        'capture_screen',
        capabilities.capture_screen?.available,
        capabilities.capture_screen?.engine,
      ],
      [
        'diagram_parser',
        capabilities.diagram_parser?.available,
        capabilities.diagram_parser?.engine,
      ],
      ['image_intake', capabilities.image_intake?.available, capabilities.image_intake?.engine],
      [
        'image_inference',
        capabilities.image_inference?.available,
        capabilities.image_inference?.reason,
      ],
      [
        'video_inference',
        capabilities.video_inference?.available,
        capabilities.video_inference?.reason,
      ],
    ];
    readinessStage.replaceChildren(
      h(
        'div',
        { class: 'vision-readiness card' },
        h('span', { class: 'micro', text: 'VISION READINESS' }),
        ...rows.map(([name, available, detail]) =>
          h(
            'div',
            { class: 'crit-row' },
            h(
              'span',
              { class: `chip ${available ? 'ok' : 'warn'}` },
              h('span', { class: 'dot' }),
              available ? 'موجود' : 'غیرفعال',
            ),
            h('span', { class: 'crit-text mono', text: name }),
            h('span', { class: 'muted crit-reason', text: detail || '—' }),
          ),
        ),
        h('span', {
          class: 'muted ag-note',
          text: 'image_intake فقط metadata می‌خواند؛ pixels_decoded و inference عمداً false هستند.',
        }),
        contract
          ? h('span', {
              class: 'muted ag-note',
              text: `قرارداد backend: ${contract.selection_allowed ? 'قابل انتخاب' : 'مسدود تا adapter واقعی'} · MIME: ${contract.image_input.accepted_mime.join(', ')} · سقف: ${contract.image_input.max_bytes} bytes`,
            })
          : null,
      ),
    );
  }

  function renderImage() {
    imageStage.replaceChildren(
      h(
        'div',
        { class: 'vision-image card' },
        h('span', { class: 'micro', text: 'SECURE IMAGE INTAKE' }),
        h('span', {
          class: 'vision-diagram-note',
          text: 'فقط فایل داخل ریشهٔ ثبت‌شده، با مسیر نسبی و سقف ۲۰MB؛ شبکه و کپی پایدار انجام نمی‌شود.',
        }),
        imageRoot,
        imagePath,
        h(
          'button',
          {
            class: 'btn',
            disabled: !capabilities?.image_intake?.available || !!busy,
            onclick: inspectImage,
          },
          'بازبینی metadata تصویر',
        ),
        imagePrompt,
        h(
          'button',
          {
            class: 'btn btn-primary',
            disabled: !contract?.selection_allowed || !!busy,
            onclick: analyzeRemote,
          },
          'تحلیل واقعی با adapter',
        ),
        imageResult
          ? h(
              'div',
              { class: 'result-panel card' },
              h('span', { class: 'micro', text: 'IMAGE METADATA — NO INFERENCE' }),
              h('div', {
                class: 'result-text',
                text: `${imageResult.format.toUpperCase()} · ${imageResult.width}×${imageResult.height} · ${imageResult.bytes} bytes`,
              }),
              h('span', { class: 'chip ok' }, h('span', { class: 'dot' }), 'فایل معتبر و محدودشده'),
              h('span', {
                class: 'muted',
                text: 'pixels_decoded=false · inference_available=false · network_sent=false',
              }),
            )
          : null,
        imageAnalysis
          ? h(
              'div',
              { class: 'result-panel card' },
              h('span', { class: 'micro', text: 'REMOTE ADAPTER RESULT' }),
              h('div', { class: 'result-text', text: imageAnalysis.answer || '' }),
              h('pre', { class: 'mono', text: JSON.stringify(imageAnalysis.provenance || {}, null, 2) }),
            )
          : null,
      ),
    );
  }

  function renderImageRoots() {
    imageRoot.replaceChildren(
      h('option', { value: '', text: 'ریشهٔ ثبت‌شده را انتخاب کنید' }),
      ...roots.map((r) => h('option', { value: r.root_id || '', text: r.name || r.root_id })),
    );
  }

  async function inspectImage() {
    if (!imageRoot.value || !imagePath.value.trim()) return;
    busy = 'در حال بررسی امن metadata تصویر…';
    error = null;
    renderStage();
    renderImage();
    try {
      imageResult = await api.visionInspectImage(imageRoot.value, imagePath.value.trim());
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStage();
      renderImage();
    }
  }

  async function analyzeRemote() {
    if (!imageRoot.value || !imagePath.value.trim() || !imagePrompt.value.trim()) return;
    if (!contract?.selection_allowed) {
      error = 'adapter تصویر هنوز پیکربندی نشده است؛ credential و model را در environment تنظیم کنید.';
      renderStage();
      renderImage();
      return;
    }
    busy = 'در حال ارسال مورد تأییدشده به adapter تصویری…';
    error = null;
    imageAnalysis = null;
    renderStage();
    renderImage();
    try {
      imageAnalysis = await api.visionAnalyzeImageRemote(
        imageRoot.value,
        imagePath.value.trim(),
        imagePrompt.value.trim(),
      );
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStage();
      renderImage();
    }
  }

  async function loadReadiness() {
    try {
      capabilities = await api.visionCapabilities();
      contract = await api.visionBackendContract();
    } catch (e) {
      error = msg(e);
    }
    try {
      roots = (await api.wsRootsList())?.roots || [];
      renderImageRoots();
    } catch {
      roots = [];
    }
    renderReadiness();
    renderImage();
    renderStage();
  }

  function renderDiagram() {
    const children = [
      h('div', { class: 'micro', text: 'DIAGRAM REVIEW' }),
      h('div', {
        class: 'vision-diagram-note',
        text: 'بازبینی ساختاری واقعی Mermaid/SVG — بدون رندر یا ادعای دیدن تصویر',
      }),
      h('div', { class: 'vision-diagram-form' }, diagramInput, diagramFormat),
      h(
        'button',
        { class: 'btn btn-primary', disabled: !!busy, onclick: inspectDiagram },
        h('span', { html: ic('search') }),
        'بازبینی نمودار',
      ),
    ];
    if (diagramResult) {
      const valid = diagramResult.valid;
      const facts = diagramResult.diagram_type
        ? `${diagramResult.diagram_type} · ${diagramResult.total_nodes ?? 0} گره · ${diagramResult.total_edges ?? 0} اتصال`
        : `${diagramResult.total_visual_elements ?? 0} عنصر بصری · ${diagramResult.has_persian_text ? 'متن فارسی دارد' : 'بدون متن فارسی'}`;
      children.push(
        h(
          'div',
          { class: `result-panel card ${valid ? '' : 'result-panel-warn'}` },
          h('span', { class: 'micro', text: 'STRUCTURE' }),
          h('div', {
            class: 'result-text',
            text: diagramResult.summary_fa || diagramResult.error || '—',
          }),
          h(
            'span',
            { class: `chip ${valid ? 'ok' : 'warn'}` },
            h('span', { class: 'dot' }),
            valid ? facts : 'ورودی معتبر نیست',
          ),
          h(
            'button',
            {
              class: 'btn btn-sm evidence-link',
              onclick: () =>
                ctx.openEvidence({
                  title: 'شواهد بازبینی نمودار',
                  steps: [
                    {
                      name: 'متن انتخابی کاربر',
                      detail: `${diagramInput.value.length} نویسه`,
                      meta: diagramFormat.value,
                    },
                    {
                      name: 'vision.inspect_diagram',
                      detail: diagramResult.summary_fa || diagramResult.error || '—',
                      meta: 'parser هسته',
                    },
                  ],
                }),
            },
            h('span', { html: ic('evidence') }),
            'شواهد بازبینی',
          ),
        ),
      );
    }
    diagramStage.replaceChildren(h('div', { class: 'vision-diagram card' }, ...children));
  }

  async function inspectDiagram() {
    const content = diagramInput.value.trim();
    if (!content) return;
    busy = 'در حال بازبینی ساختار نمودار…';
    error = null;
    renderStage();
    renderDiagram();
    try {
      diagramResult = await api.visionInspectDiagram(content, diagramFormat.value);
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStage();
      renderDiagram();
    }
  }

  async function capture() {
    busy = 'در حال عکس‌گرفتن از صفحه و استخراج متن…';
    error = null;
    result = null;
    pdfResult = null;
    renderStage();
    try {
      const res = await api.visionCaptureScreen('general');
      if (res?.success === false) {
        error = res.error || 'عکس‌گرفتن از صفحه ناموفق بود';
      } else {
        result = res;
      }
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStage();
    }
  }

  async function exportPdf() {
    try {
      const folder = await pickFolder('پوشه‌ی مقصد برای گزارش PDF');
      if (!folder) return;
      busy = 'pdf';
      renderStage();
      const report = {
        title: 'متن استخراج‌شده از صفحه',
        subtitle: 'vision.capture_screen — اسکرین‌شات بلافاصله حذف شد',
        sections: [
          {
            heading: 'متن صفحه',
            paragraphs: [result.text],
            kpis: [
              { label: 'موتور', value: result.engine || 'OCR هسته' },
              { label: 'نویسه', value: String(result.text.length) },
            ],
          },
        ],
      };
      const out = `${folder.replace(/[\\/]+$/, '')}/screen-scan.report.pdf`;
      pdfResult = await api.pdfExport(report, out);
      pdfEvidence = {
        title: 'گزارش بینایی صفحه',
        steps: [
          { name: 'vision.capture_screen', detail: 'GDI + حذف فوری اسکرین‌شات', meta: 'P-14' },
          { name: 'ocr', detail: `${result.text.length} نویسه`, meta: result.engine || 'هسته' },
          {
            name: 'pdf.export_report',
            detail: pdfResult.file_path,
            meta: fmtBytes(pdfResult.bytes ?? 0),
          },
        ],
      };
    } catch (e) {
      pdfResult = null;
      error = msg(e);
    } finally {
      busy = '';
      renderStage();
    }
  }

  root.append(
    h(
      'div',
      { class: 'vision-view' },
      h(
        'div',
        { class: 'voice-toolbar' },
        h(
          'button',
          { class: 'btn btn-primary', onclick: capture },
          h('span', { html: ic('eye') }),
          'عکس‌گرفتن از صفحه',
        ),
      ),
      stage,
      readinessStage,
      imageStage,
      diagramStage,
    ),
  );

  renderStage();
  renderReadiness();
  renderImageRoots();
  renderImage();
  renderDiagram();
  loadReadiness();
}
