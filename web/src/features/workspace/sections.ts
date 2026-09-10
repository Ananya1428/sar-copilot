/**
 * Mirrors api/app/domain/narrative/sections.py NARRATIVE_SECTIONS — the
 * real section schema the backend generates section-by-section (blueprint
 * §13.5). Used for the generation skeleton's section labels and for
 * grouping/labelling sentences in the rendered narrative.
 */
export const NARRATIVE_SECTIONS = [
  { id: "introduction", label: "Introduction and basis for filing" },
  { id: "who", label: "Subject identification" },
  { id: "what_when", label: "Activity description and timeline" },
  { id: "where", label: "Locations and jurisdictions" },
  { id: "how", label: "Mechanics of the activity" },
  { id: "why", label: "Basis for suspicion" },
  { id: "conclusion", label: "Actions taken and retention" },
] as const;

export function sectionLabel(sectionId: string | null): string {
  return NARRATIVE_SECTIONS.find((s) => s.id === sectionId)?.label ?? sectionId ?? "Section";
}
