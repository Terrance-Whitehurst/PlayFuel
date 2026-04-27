-- 0006_plan_llm_summary.sql
-- Adds llm_summary jsonb column to plans for Phase 6 LLM explanation layer.
-- Nullable: pre-Phase-6 plans will have NULL; Phase-6+ plans will have a
-- structured PlanExplanation JSON produced by TemplateProvider or a real LLM.
-- Resolves OQ-LLM-0 (persistence of LLM output alongside plan_json).
ALTER TABLE public.plans
  ADD COLUMN IF NOT EXISTS llm_summary jsonb;

COMMENT ON COLUMN public.plans.llm_summary IS
  'Structured PlanExplanation produced by the LLM (or TemplateProvider fallback). '
  'Nullable — NULL for plans generated before Phase 6.';
