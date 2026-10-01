/** Types mirroring the Weather Risk API (POST /chat, GET /chat/sessions, GET /hubs). */

export type HazardType = 'winter' | 'flood' | 'hurricane' | 'heat';
export type ActionStatus = 'success' | 'error' | 'skipped';

export interface Hub {
  id: string;
  name: string;
  state: string;
  region: string;
  location: { latitude: number; longitude: number };
}

export interface ActionRecord {
  capability: string;
  arguments: Record<string, unknown>;
  status: ActionStatus;
  duration_ms: number;
  error: string | null;
}

/** Deterministic data behind an answer, exactly as the capability returned it. */
export interface CapabilityResult {
  capability: string;
  arguments: Record<string, unknown>;
  data: Record<string, any>;
  warnings: string[];
}

export interface ChatRequest {
  session_id?: string;
  message: string;
  /** Same id on a retry, so the server replaces the turn instead of adding a copy. */
  turn_id?: string;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  actions_performed: ActionRecord[];
  warnings: string[];
  results: CapabilityResult[];
}

/** A stored conversation in the list (GET /chat/sessions). */
export interface SessionSummary {
  session_id: string;
  /** The session's first question. */
  title: string;
  created_at: string;
  updated_at: string;
  turn_count: number;
}

/** One stored question with its full answer (same fields as a /chat response). */
export interface StoredTurn {
  turn_id: string;
  question: string;
  asked_at: string;
  answer: string;
  answered_at: string;
  actions_performed: ActionRecord[];
  warnings: string[];
  results: CapabilityResult[];
}

/** GET /chat/sessions/{session_id} */
export interface Conversation {
  session_id: string;
  turns: StoredTurn[];
}

// --- Shapes of `CapabilityResult.data` per capability (subset used by the UI) ---------

export interface Period {
  start: string;
  end: string;
  days?: number;
}

export interface RiskFactor {
  name: string;
  description: string;
  raw_value: number;
  unit: string;
  scale: [number, number];
  normalized_score: number;
  weight: number;
  contribution: number;
}

export interface HazardAssessment {
  hazard: HazardType;
  score: number;
  weight_in_overall: number;
  contribution_to_overall: number;
  factors: RiskFactor[];
  assumptions: string[];
  warnings: string[];
}

export interface HubAssessment {
  hub_id: string;
  hub_name: string;
  region: string;
  period: Period;
  overall_score: number;
  hazards: HazardAssessment[];
  assumptions: string[];
  warnings: string[];
}

export interface RankingData {
  hazards: HazardType[];
  applied_weights: Partial<Record<HazardType, number>>;
  rankings: {
    rank: number;
    hub_id: string;
    hub_name: string;
    overall_score: number;
    hazard_scores: Partial<Record<HazardType, number>>;
  }[];
  assessments: HubAssessment[];
}

export interface ComparisonData {
  hub_ids: string[];
  highest_overall_hub_id: string;
  overall_scores: Record<string, number>;
  overall_differences: { hub_id: string; other_hub_id: string; difference: number }[];
  hazard_comparisons: {
    hazard: HazardType;
    scores: Record<string, number>;
    highest_hub_id: string;
    lowest_hub_id: string;
    spread: number;
  }[];
  assessments: HubAssessment[];
}
