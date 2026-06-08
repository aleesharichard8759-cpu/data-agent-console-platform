import { useState } from "react";
import type { ReactNode } from "react";
import type { Environment, Language, NavGroup, RouteKey, Translate, UserRole } from "../types";

interface LayoutProps {
  activeRoute: RouteKey;
  environment: Environment;
  language: Language;
  navGroups: NavGroup[];
  tenant: string;
  userRole: UserRole;
  apiMode: "mock" | "real";
  children: ReactNode;
  t: Translate;
  onNavigate: (route: RouteKey) => void;
  onEnvironmentChange: (environment: Environment) => void;
  onLanguageChange: (language: Language) => void;
  onTenantChange: (tenant: string) => void;
  onUserRoleChange: (role: UserRole) => void;
  onApiModeChange: (mode: "mock" | "real") => void;
  onResetMockState: () => void;
  onExportConfig: () => void;
}

const environments: Environment[] = ["dev", "test", "staging", "prod"];
const languages: Language[] = ["zh-CN", "en-US"];
const environmentLabels: Record<Environment, string> = {
  dev: "开发",
  test: "测试",
  staging: "预发",
  prod: "生产"
};

export function Layout({
  activeRoute,
  environment,
  language,
  navGroups,
  tenant,
  userRole,
  apiMode,
  children,
  t,
  onNavigate,
  onEnvironmentChange,
  onLanguageChange,
  onTenantChange,
  onUserRoleChange,
  onApiModeChange,
  onResetMockState,
  onExportConfig
}: LayoutProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    () => new Set(["Runtime 配置中心", "Data&QA 产品配置"])
  );
  const [healthStatus, setHealthStatus] = useState<"unchecked" | "checking" | "healthy" | "unavailable">("unchecked");

  const checkHealth = async () => {
    setHealthStatus("checking");
    try {
      const response = await fetch("/api/health");
      setHealthStatus(response.ok ? "healthy" : "unavailable");
    } catch {
      setHealthStatus("unavailable");
    }
  };

  const toggleGroup = (label: string) => {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">DA</div>
          <div>
            <h1>Data Agent Console</h1>
            <p>Runtime + Data&QA</p>
          </div>
        </div>
        <nav className="nav-stack" aria-label="Data Agent Console navigation">
          {navGroups.map((group) => {
            const hasActiveRoute = group.items.some((item) => item.route === activeRoute);
            const isCollapsible = group.items.length > 1;
            const isCollapsed = isCollapsible && collapsedGroups.has(group.label) && !hasActiveRoute;
            return (
              <section key={group.label} className={hasActiveRoute ? "nav-group active-group" : "nav-group"}>
                <button
                  type="button"
                  className="nav-group-toggle"
                  onClick={() => (isCollapsible ? toggleGroup(group.label) : undefined)}
                  aria-expanded={!isCollapsed}
                >
                  <span>{t(group.label)}</span>
                  {isCollapsible ? <strong>{isCollapsed ? "+" : "-"}</strong> : null}
                </button>
                {!isCollapsed
                  ? group.items.map((item) => (
                      <button
                        key={`${group.label}-${item.route}`}
                        type="button"
                        className={item.route === activeRoute ? "nav-item active" : "nav-item"}
                        onClick={() => onNavigate(item.route)}
                      >
                        <span>{t(item.label)}</span>
                      </button>
                    ))
                  : null}
              </section>
            );
          })}
        </nav>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="topbar-left">
            <p className="topbar-label">{t("当前环境")}</p>
            <div className="env-switch" role="group" aria-label="Environment switcher">
              {environments.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={item === environment ? "env-chip active" : "env-chip"}
                  onClick={() => onEnvironmentChange(item)}
                >
                  {t(environmentLabels[item])}
                </button>
              ))}
            </div>
          </div>
          <div className="topbar-right">
            <button type="button" className="settings-button" onClick={() => setSettingsOpen((current) => !current)}>
              {t("设置")}
            </button>
            {settingsOpen ? (
              <section className="settings-popover" aria-label={t("平台设置")}>
                <div className="settings-section">
                  <p className="topbar-label">{t("语言设置")}</p>
                  <div className="env-switch" role="group" aria-label="Language switcher">
                    {languages.map((item) => (
                      <button
                        key={item}
                        type="button"
                        className={item === language ? "env-chip active" : "env-chip"}
                        onClick={() => onLanguageChange(item)}
                      >
                        {item === "zh-CN" ? t("中文") : t("English")}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="settings-section">
                  <p className="topbar-label">{t("版本信息")}</p>
                  <div className="release-pill">
                    <span>{t("Runtime 版本")}</span>
                    <strong>0.00.1</strong>
                  </div>
                  <div className="release-pill">
                    <span>{t("Data&QA 版本")}</span>
                    <strong>0.00.1</strong>
                  </div>
                </div>
                <div className="settings-section">
                  <p className="topbar-label">{t("运行上下文")}</p>
                  <label className="compact-field">
                    <span>{t("当前租户")}</span>
                    <select value={tenant} onChange={(event) => onTenantChange(event.target.value)}>
                      <option value="loctek">{t("乐歌租户")}</option>
                      <option value="demo">{t("演示租户")}</option>
                    </select>
                  </label>
                  <label className="compact-field">
                    <span>{t("当前角色")}</span>
                    <select value={userRole} onChange={(event) => onUserRoleChange(event.target.value as UserRole)}>
                      <option value="platform_admin">{t("平台管理员")}</option>
                      <option value="data_product_manager">{t("数据产品经理")}</option>
                      <option value="data_team">{t("数据团队")}</option>
                      <option value="security_reviewer">{t("安全合规")}</option>
                    </select>
                  </label>
                </div>
                <div className="settings-section">
                  <p className="topbar-label">{t("API 模式")}</p>
                  <div className="env-switch" role="group" aria-label="API mode switcher">
                    <button type="button" className={apiMode === "mock" ? "env-chip active" : "env-chip"} onClick={() => onApiModeChange("mock")}>
                      Mock
                    </button>
                    <button type="button" className={apiMode === "real" ? "env-chip active" : "env-chip"} onClick={() => onApiModeChange("real")}>
                      Real
                    </button>
                  </div>
                  <div className="settings-row">
                    <span className={`tag status-${healthStatus === "healthy" ? "active" : healthStatus === "unavailable" ? "open" : "tracking"}`}>
                      {t("后端健康")}：{t(healthStatus)}
                    </span>
                    <button type="button" className="ghost-button" onClick={checkHealth}>
                      {t("检查")}
                    </button>
                  </div>
                </div>
                <div className="settings-section settings-actions">
                  <button type="button" className="secondary-button" onClick={onExportConfig}>
                    {t("导出当前配置 JSON")}
                  </button>
                  <button type="button" className="ghost-button danger" onClick={onResetMockState}>
                    {t("清空本地 mock state")}
                  </button>
                </div>
              </section>
            ) : null}
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
