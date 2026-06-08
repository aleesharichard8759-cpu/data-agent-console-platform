export type Environment = "dev" | "test" | "staging" | "prod";
export type Language = "zh-CN" | "en-US";
export type Translate = (value: string) => string;
export type UserRole = "platform_admin" | "data_product_manager" | "data_team" | "security_reviewer";

export type RouteKey =
  | "dashboard"
  | "runtime-workbench"
  | "dataqa-workspace"
  | "runtime-overview"
  | "connectors"
  | "datatools"
  | "policy-engine"
  | "sql-gateway"
  | "dlp-masking"
  | "approval-center"
  | "agent-apps"
  | "semantic-layer"
  | "analysis-workflow"
  | "case-library"
  | "eval-runs"
  | "bad-case-workbench"
  | "trace-audit"
  | "release-center";

export type FieldType = "text" | "textarea" | "select" | "number" | "checkbox";

export interface FieldConfig {
  key: string;
  label: string;
  type: FieldType;
  required?: boolean;
  options?: string[];
  placeholder?: string;
}

export interface ColumnConfig {
  key: string;
  label: string;
  tone?: "default" | "status" | "risk" | "decision";
}

export interface MetricCard {
  label: string;
  value: string;
  delta: string;
  tone: "green" | "blue" | "amber" | "red" | "slate";
}

export interface EntityRow {
  id: string;
  name: string;
  status: string;
  owner: string;
  [key: string]: string | number | boolean | string[];
}

export interface PageConfig {
  route: RouteKey;
  title: string;
  eyebrow: string;
  description: string;
  mode: "read" | "config" | "run";
  primaryAction: string;
  modalTitle: string;
  guardrail: string;
  metrics: MetricCard[];
  columns: ColumnConfig[];
  fields: FieldConfig[];
  records: EntityRow[];
}

export interface NavItem {
  route: RouteKey;
  label: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export interface JourneyStep {
  label: string;
  route: RouteKey;
  status: "done" | "current" | "todo";
}

export interface UserJourney {
  id: string;
  title: string;
  user: string;
  role: UserRole;
  outcome: string;
  primaryRoute: RouteKey;
  steps: JourneyStep[];
}

export interface PageGuidance {
  goal: string;
  primaryTask: string;
  nextLabel: string;
  nextRoute?: RouteKey;
}
