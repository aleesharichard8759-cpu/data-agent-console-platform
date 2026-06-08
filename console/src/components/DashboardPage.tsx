import type { EntityRow, MetricCard, RouteKey, Translate, UserJourney, UserRole } from "../types";

interface DashboardPageProps {
  records: EntityRow[];
  metrics: MetricCard[];
  journeys: UserJourney[];
  userRole: UserRole;
  onNavigate: (route: RouteKey) => void;
  t: Translate;
}

const roleOwnerLabels: Record<UserRole, string[]> = {
  platform_admin: ["平台管理员"],
  data_product_manager: ["数据产品经理"],
  data_team: ["数据团队", "数据分析师", "数据开发"],
  security_reviewer: ["安全合规"]
};

const roleDefaultRoutes: Record<UserRole, RouteKey> = {
  platform_admin: "connectors",
  data_product_manager: "agent-apps",
  data_team: "case-library",
  security_reviewer: "approval-center"
};

const roleScopes: Partial<Record<UserRole, string[]>> = {
  platform_admin: ["Runtime"],
  data_product_manager: ["Eval"],
  data_team: ["Eval"],
  security_reviewer: ["Audit"]
};

function toneClass(tone: MetricCard["tone"]) {
  return `metric-card tone-${tone}`;
}

function statusTag(value: EntityRow[string]) {
  return <span className={`tag status-${String(value).toLowerCase()}`}>{String(value)}</span>;
}

function riskTag(value: EntityRow[string]) {
  return <span className={`tag risk-${String(value).toLowerCase()}`}>{String(value)}</span>;
}

export function DashboardPage({ records, metrics, journeys, userRole, onNavigate, t }: DashboardPageProps) {
  const ownerLabels = roleOwnerLabels[userRole];
  const visibleJourneys = journeys.filter((journey) => journey.role === userRole);
  const roleRecords = records.filter((record) => ownerLabels.includes(String(record.owner)));
  const scopedRecords = records.filter((record) => (roleScopes[userRole] ?? []).includes(String(record.scope)));
  const visibleRecords = roleRecords.length ? roleRecords : scopedRecords;
  const focusItems = (visibleRecords.length ? visibleRecords : records).slice(0, 3);

  return (
    <section className="page dashboard-page">
      <div className="page-header dashboard-header">
        <div>
          <p className="eyebrow">{t("运营驾驶舱")}</p>
          <h2>Data Agent Console</h2>
          <p className="description">
            {t("先处理阻断项，再按用户路径推进接入、问数和上线验证。")}
          </p>
        </div>
        <div className="page-actions">
          <button type="button" className="primary-button" onClick={() => onNavigate("connectors")}>
            {t("接入新数据源")}
          </button>
          <button type="button" className="secondary-button" onClick={() => onNavigate("eval-runs")}>
            {t("运行上线评测")}
          </button>
        </div>
      </div>

      <section className="focus-strip" aria-label={t("今日最重要 3 件事")}>
        <div className="focus-title">
          <p className="eyebrow">{t("今日最重要 3 件事")}</p>
          <h3>{t("先解除上线和生产安全阻断")}</h3>
        </div>
        <div className="focus-grid">
          {focusItems.map((record) => (
            <button key={record.id} type="button" className="focus-card" onClick={() => onNavigate(String(record.scope) === "Eval" ? "eval-runs" : String(record.scope) === "Audit" ? "approval-center" : "runtime-workbench")}>
              <span>{t(String(record.scope))}</span>
              <strong>{t(String(record.name))}</strong>
              <div className="todo-tags">
                {statusTag(record.status)}
                {riskTag(record.risk)}
              </div>
            </button>
          ))}
        </div>
      </section>

      <div className="metric-grid">
        {metrics.map((metric) => (
          <article key={metric.label} className={toneClass(metric.tone)}>
            <p>{t(metric.label)}</p>
            <strong>{t(metric.value)}</strong>
            <span>{t(metric.delta)}</span>
          </article>
        ))}
      </div>

      <section className="journey-flow" aria-label={t("主用户路径")}>
        {visibleJourneys.length ? visibleJourneys.map((journey) => (
          <article key={journey.id} className="journey-card compact">
            <div className="journey-card-header">
              <div>
                <p>{t(journey.user)}</p>
                <h3>{t(journey.title)}</h3>
              </div>
              <button type="button" className="primary-button" onClick={() => onNavigate(journey.primaryRoute)}>
                {t("开始")}
              </button>
            </div>
            <p className="journey-outcome">{t(journey.outcome)}</p>
            <ol className="journey-steps">
              {journey.steps.map((step, index) => (
                <li key={`${journey.id}-${index}-${step.route}`} className={`journey-step is-${step.status}`}>
                  <button type="button" onClick={() => onNavigate(step.route)}>
                    <span>{index + 1}</span>
                    {t(step.label)}
                  </button>
                </li>
              ))}
            </ol>
          </article>
        )) : (
          <article className="journey-card compact role-empty">
            <div className="journey-card-header">
              <div>
                <p>{t("当前角色")}</p>
                <h3>{t("暂无专属工作流")}</h3>
              </div>
              <button type="button" className="primary-button" onClick={() => onNavigate(roleDefaultRoutes[userRole])}>
                {t("进入相关页面")}
              </button>
            </div>
            <p className="journey-outcome">{t("该角色当前没有独立用户路径，已收敛到相关待办和运营入口。")}</p>
            <ol className="journey-steps">
              <li className="journey-step is-current">
                <button type="button" onClick={() => onNavigate(roleDefaultRoutes[userRole])}>
                  <span>1</span>
                  {t("处理角色相关事项")}
                </button>
              </li>
            </ol>
          </article>
        )}
      </section>

      <div className="dashboard-panels">
        <section className="panel">
          <div className="panel-toolbar">
            <div>
              <h3>{t("今日待办")}</h3>
              <p>{t("优先处理阻断上线或生产安全的问题")}</p>
            </div>
            <button type="button" className="ghost-button" onClick={() => onNavigate("trace-audit")}>
              {t("查看审计")}
            </button>
          </div>
          <div className="todo-list">
            {(visibleRecords.length ? visibleRecords : records).map((record) => (
              <article key={record.id} className="todo-row">
                <div>
                  <strong>{t(String(record.name))}</strong>
                  <span>{t(String(record.scope))}</span>
                </div>
                <div className="todo-tags">
                  {statusTag(record.status)}
                  {riskTag(record.risk)}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-toolbar">
            <div>
              <h3>{t("闭环能力缺口")}</h3>
              <p>{t("从配置平台补齐到可运营 Agent 平台")}</p>
            </div>
          </div>
          <div className="sequence-list">
            <button type="button" onClick={() => onNavigate("approval-center")}>
              <strong>{t("审批中心")}</strong>
              <span>{t("统一处理 Plan Mode、高风险 SQL、发布和回滚审批")}</span>
            </button>
            <button type="button" onClick={() => onNavigate("bad-case-workbench")}>
              <strong>{t("Bad Case 工作台")}</strong>
              <span>{t("把负反馈转成归因、修复、回归和发布验证")}</span>
            </button>
            <button type="button" onClick={() => onNavigate("release-center")}>
              <strong>{t("发布中心")}</strong>
              <span>{t("对比环境差异、发布前检查并保留回滚入口")}</span>
            </button>
            <button type="button" onClick={() => onNavigate("dlp-masking")}>
              <strong>{t("DLP / Masking")}</strong>
              <span>{t("补齐字段级敏感标签、动态脱敏和导出限制")}</span>
            </button>
          </div>
        </section>
      </div>
    </section>
  );
}
