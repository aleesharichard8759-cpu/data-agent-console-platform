import { useEffect, useMemo, useState } from "react";
import { ConfigPage } from "./components/ConfigPage";
import { DashboardPage } from "./components/DashboardPage";
import { DataQAWorkspacePage } from "./components/DataQAWorkspacePage";
import { Layout } from "./components/Layout";
import { RuntimeWorkbenchPage } from "./components/RuntimeWorkbenchPage";
import { navGroups, pageConfigByRoute, pageConfigs, routePaths, userJourneys } from "./data/mockData";
import { createTranslator } from "./i18n";
import type { EntityRow, Environment, Language, RouteKey, UserRole } from "./types";

const pathToRoute = Object.fromEntries(Object.entries(routePaths).map(([route, path]) => [path, route])) as Record<string, RouteKey>;

function routeFromHash(): RouteKey {
  const path = window.location.hash.replace(/^#/, "") || "/";
  return pathToRoute[path] ?? "dashboard";
}

function buildInitialRows() {
  return Object.fromEntries(pageConfigs.map((page) => [page.route, page.records])) as Partial<Record<RouteKey, EntityRow[]>>;
}

function App() {
  const [activeRoute, setActiveRoute] = useState<RouteKey>(() => routeFromHash());
  const [environment, setEnvironment] = useState<Environment>("prod");
  const [language, setLanguage] = useState<Language>("zh-CN");
  const [tenant, setTenant] = useState("loctek");
  const [userRole, setUserRole] = useState<UserRole>("platform_admin");
  const [apiMode, setApiMode] = useState<"mock" | "real">("mock");
  const [rowsByRoute, setRowsByRoute] = useState<Partial<Record<RouteKey, EntityRow[]>>>(() => buildInitialRows());

  useEffect(() => {
    const syncRoute = () => setActiveRoute(routeFromHash());
    window.addEventListener("hashchange", syncRoute);
    return () => window.removeEventListener("hashchange", syncRoute);
  }, []);

  const activePage = pageConfigByRoute[activeRoute] ?? pageConfigByRoute.dashboard;
  const t = useMemo(() => createTranslator(language), [language]);

  const navigate = (route: RouteKey) => {
    window.location.hash = routePaths[route];
    setActiveRoute(route);
  };

  const resetMockState = () => {
    setRowsByRoute(buildInitialRows());
  };

  const exportConfig = () => {
    const payload = {
      tenant,
      userRole,
      apiMode,
      environment,
      exportedAt: new Date().toISOString(),
      rowsByRoute
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "data-agent-console-config.json";
    link.click();
    URL.revokeObjectURL(url);
  };

  const rows = useMemo(() => rowsByRoute[activePage.route] ?? [], [activePage.route, rowsByRoute]);

  return (
    <Layout
      activeRoute={activeRoute}
      environment={environment}
      language={language}
      navGroups={navGroups}
      tenant={tenant}
      userRole={userRole}
      apiMode={apiMode}
      t={t}
      onNavigate={navigate}
      onEnvironmentChange={setEnvironment}
      onLanguageChange={setLanguage}
      onTenantChange={setTenant}
      onUserRoleChange={setUserRole}
      onApiModeChange={setApiMode}
      onResetMockState={resetMockState}
      onExportConfig={exportConfig}
    >
      {activeRoute === "runtime-workbench" ? (
        <RuntimeWorkbenchPage t={t} />
      ) : activeRoute === "dataqa-workspace" ? (
        <DataQAWorkspacePage language={language} t={t} />
      ) : activePage.route === "dashboard" ? (
        <DashboardPage records={rows} metrics={activePage.metrics} journeys={userJourneys} userRole={userRole} onNavigate={navigate} t={t} />
      ) : (
        <ConfigPage
          page={activePage}
          rows={rows}
          onRowsChange={(nextRows) => setRowsByRoute((current) => ({ ...current, [activePage.route]: nextRows }))}
          onNavigate={navigate}
          t={t}
        />
      )}
    </Layout>
  );
}

export default App;
