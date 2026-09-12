"""Genetic algorithm arena and Elo-based strategy matchmaking."""

from __future__ import annotations

import math
import random
import uuid

from dream.evolution.types import EvolutionMutationType, StrategyGene


class StrategyEvolutionArena:
    """Evolutionary tournament arena evaluating strategy genes using Elo rating."""

    def __init__(self, k_factor: float = 32.0) -> None:
        self.k_factor = k_factor
        self._gene_pool: dict[str, StrategyGene] = {}
        self._seed_default_genes()

    def _seed_default_genes(self) -> None:
        """Seed arena with baseline strategy archetypes."""
        g1 = StrategyGene(
            gene_id="strat_delphi_reasoner",
            name="Delphi Multi-Agent Consensus",
            description_fa="استراتژی اجماع چندعامله مبتنی بر داوری و پالایش خطای فکت‌ها",
            prompt_template="شما یک تحلیل‌گر دقیق هستید. پاسخ‌ها را اعتبارسنجی کنید.",
            heuristics=["همواره نتایج ابزارهای ریاضی را دو بار بررسی کن."],
            preferred_tools=["calculate", "get_datetime"],
            elo_rating=1250.0,
            fitness_score=0.82,
        )
        g2 = StrategyGene(
            gene_id="strat_speculative_fast",
            name="Speculative Low-Latency",
            description_fa="استراتژی پیش‌اجرای حدسی و فشرده‌سازی حافظه با حداقل تاخیر",
            prompt_template="پاسخ‌های خلاصه، دقیق و بدون حاشیه‌پردازی ارائه بده.",
            heuristics=["پاسخ مستقیم را در اولویت قرار بده مگر ابزار ضروری باشد."],
            preferred_tools=["list_notes", "calculate"],
            elo_rating=1210.0,
            fitness_score=0.79,
        )
        g3 = StrategyGene(
            gene_id="strat_persian_linguist",
            name="Persian Semantic Grounding",
            description_fa="استراتژی انطباق زبانی، رسم‌الخط، گاهشماری جلالی و اصطلاحات بومی",
            prompt_template="رعایت کامل نیم‌فاصله، ساختار فارسی استاندارد و لحن محترمانه.",
            heuristics=["جایگزینی حروف عربی با حروف استاندارد فارسی."],
            preferred_tools=["get_datetime"],
            elo_rating=1280.0,
            fitness_score=0.88,
        )
        for g in (g1, g2, g3):
            self._gene_pool[g.gene_id] = g

    def register_gene(self, gene: StrategyGene) -> None:
        """Add a new strategy gene into the pool."""
        self._gene_pool[gene.gene_id] = gene

    def get_gene(self, gene_id: str) -> StrategyGene | None:
        """Retrieve strategy gene by identifier."""
        return self._gene_pool.get(gene_id)

    def get_leaderboard(self) -> list[StrategyGene]:
        """Return leaderboard sorted by Elo rating descending."""
        return sorted(self._gene_pool.values(), key=lambda g: g.elo_rating, reverse=True)

    def run_pairwise_match(
        self,
        gene_a_id: str,
        gene_b_id: str,
        winner_id: str | None = None,
    ) -> tuple[float, float]:
        """Execute a match between two strategies and update their Elo ratings."""
        g_a = self._gene_pool.get(gene_a_id)
        g_b = self._gene_pool.get(gene_b_id)
        if not g_a or not g_b:
            raise KeyError("Strategy gene not found in pool.")

        # Calculate expected scores
        exp_a = 1.0 / (1.0 + math.pow(10, (g_b.elo_rating - g_a.elo_rating) / 400.0))
        exp_b = 1.0 / (1.0 + math.pow(10, (g_a.elo_rating - g_b.elo_rating) / 400.0))

        if winner_id == gene_a_id:
            score_a, score_b = 1.0, 0.0
            g_a.wins += 1
            g_b.losses += 1
        elif winner_id == gene_b_id:
            score_a, score_b = 0.0, 1.0
            g_b.wins += 1
            g_a.losses += 1
        else:
            # Deterministic comparison based on fitness_score
            if g_a.fitness_score >= g_b.fitness_score:
                score_a, score_b = 1.0, 0.0
                g_a.wins += 1
                g_b.losses += 1
            else:
                score_a, score_b = 0.0, 1.0
                g_b.wins += 1
                g_a.losses += 1

        # Update Elo ratings
        g_a.elo_rating += self.k_factor * (score_a - exp_a)
        g_b.elo_rating += self.k_factor * (score_b - exp_b)

        g_a.matches_played += 1
        g_b.matches_played += 1

        return round(g_a.elo_rating, 1), round(g_b.elo_rating, 1)

    def mutate_gene(
        self,
        parent_id: str,
        mutation_type: EvolutionMutationType = EvolutionMutationType.HEURISTIC_RULE_ADDITION,
        new_heuristic: str = "",
    ) -> StrategyGene:
        """Create an evolved offspring gene with mutated prompt or heuristics."""
        parent = self._gene_pool.get(parent_id)
        if not parent:
            raise KeyError(f"Parent gene '{parent_id}' not found.")

        offspring_id = f"strat_mut_{uuid.uuid4().hex[:6]}"
        heuristics = list(parent.heuristics)
        prompt_tmpl = parent.prompt_template

        if mutation_type == EvolutionMutationType.HEURISTIC_RULE_ADDITION and new_heuristic:
            heuristics.append(new_heuristic)
        elif mutation_type == EvolutionMutationType.PROMPT_REFINEMENT:
            prompt_tmpl += " توجه ویژه به صحت داده‌ها و ساختار شفاف پاسخ."

        mutated = StrategyGene(
            gene_id=offspring_id,
            name=f"{parent.name} (Gen {parent.generation + 1})",
            description_fa=f"جهش‌یافته از {parent.name} با الگوی {mutation_type.value}",
            prompt_template=prompt_tmpl,
            heuristics=heuristics,
            preferred_tools=list(parent.preferred_tools),
            fitness_score=min(0.99, parent.fitness_score + random.uniform(0.02, 0.05)),
            elo_rating=parent.elo_rating + random.uniform(10.0, 30.0),
            generation=parent.generation + 1,
        )

        self._gene_pool[offspring_id] = mutated
        return mutated
