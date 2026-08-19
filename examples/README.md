# Sample data files

This directory holds sample data for exercising Dream's data pipeline and
formatting features without any real customer data.

## `iranian-sales-sample.csv`

A small, hand-made sales extract with Persian headers (date, customer,
product category, product name, quantity, unit price in rial, and line
total in rial). All rows are fictional. The dates are Jalali (e.g.
`1404-05-14`), which is what a real Iranian ERP export looks like. Encoded
as plain UTF-8 (no BOM).

## `iranian-sales-cp1256.csv`

The same kind of extract saved the way older Iranian Windows office apps
still emit files: **Windows-1256 (cp1256)** bytes, Arabic yeh/kaf in the
headers (`تاريخ`, `قيمت`), Latin digits. The on-disk file is *not* valid
UTF-8 — `load_data` has to sniff cp1256 to read it.

## `iranian-sales-utf8-sig.csv`

UTF-8 **with BOM** (`EF BB BF`), Farsi yeh/kaf in the headers, and Persian
digits (`۱۲۳`) in the numeric cells. `load_data` must strip the BOM so the
first column is `تاریخ` rather than `\ufeffتاریخ`, and fold Persian digits
to Latin before numeric coerce.

You can load any of them in a Dream data-science session:

```text
load_data examples/iranian-sales-sample.csv
load_data examples/iranian-sales-cp1256.csv
load_data examples/iranian-sales-utf8-sig.csv
profile_data
analyze_data ...
```

The files are intentionally tiny so the full pipeline runs offline and
fast; the point is the shape and the encoding, not the size.
