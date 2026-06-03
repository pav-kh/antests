export type Level = "base" | "specialist";
export type Mode = "exam" | "adaptive";
export type SessionStatus = "generating" | "ready" | "in_progress" | "finished" | "failed";
export type ArtifactKind = "none" | "code" | "json" | "sql" | "xml" | "mermaid";
export type QuestionType = "single" | "multi";

export interface Option { key: string; text: string; }

export interface Question {
  id: string;
  seq: number;
  topic_id: string;
  type: QuestionType;
  stem: string;
  artifact_kind: ArtifactKind;
  artifact_content: string | null;
  options: Option[];
}

export interface SessionStatusResponse {
  id: string;
  status: SessionStatus;
  level: Level;
  mode: Mode;
  total_questions: number;
  generated_count: number;
  time_limit_sec: number;
  timer_started_at: string | null;
}

export interface TopicBreakdown {
  topic_id: string;
  answered: number;
  correct: number;
  accuracy: number;
}

export interface QuestionReview extends Question {
  correct_keys: string[];
  selected_keys: string[];
  is_correct: boolean;
  explanation: string;
}

export interface Results {
  session_id: string;
  level: Level;
  mode: Mode;
  score_percent: number;
  passed: boolean;
  total_questions: number;
  answered_count: number;
  topic_breakdown: TopicBreakdown[];
  recommendation: string;
  questions: QuestionReview[];
}

export interface User { id: string; login: string; }
