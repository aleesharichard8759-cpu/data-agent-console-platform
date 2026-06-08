import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { pageGuidance } from "../data/mockData";
import { displayLabel } from "../displayLabels";
import type { ColumnConfig, EntityRow, FieldConfig, PageConfig, RouteKey, Translate } from "../types";

interface ConfigPageProps {
  page: PageConfig;
  rows: EntityRow[];
  onRowsChange: (rows: EntityRow[]) => void;
  onNavigate: (route: RouteKey) => void;
  t: Translate;
}

type FormState = Record<string, string | number | boolean | string[]>;

function emptyForm(fields: FieldConfig[]): FormState {
  return Object.fromEntries(
    fields.map((field) => {
      if (field.type === "checkbox") return [field.key, false];
      if (field.type === "number") return [field.key, 0];
      return [field.key, field.options?.[0] ?? ""];
    })
  );
}

function createId(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}`;
}

function statusClass(value: string, tone?: ColumnConfig["tone"]) {
  const normalized = value.toLowerCase();
  if (tone === "decision") return `tag decision-${normalized}`;
  if (tone === "risk") return `tag risk-${normalized}`;
  if (tone === "status") return `tag status-${normalized}`;
  return "table-text";
}

function displayCell(value: EntityRow[string], column: ColumnConfig, t: Translate) {
  const text = Array.isArray(value) ? value.map((item) => displayLabel(item, t)).join(", ") : displayLabel(value, t);
  if (!column.tone) return <span className="table-text">{text}</span>;
  const classValue = Array.isArray(value) ? String(value[0] ?? "") : String(value ?? "");
  return <span className={statusClass(classValue, column.tone)}>{text}</span>;
}

function FormField({
  field,
  value,
  onChange,
  t,
  disabled = false
}: {
  field: FieldConfig;
  value: FormState[string];
  onChange: (key: string, value: FormState[string]) => void;
  t: Translate;
  disabled?: boolean;
}) {
  const id = `field-${field.key}`;

  if (field.type === "textarea") {
    return (
      <label className="form-field" htmlFor={id}>
        <span>{t(field.label)}</span>
        <textarea
          id={id}
          value={String(value ?? "")}
          placeholder={field.placeholder ? t(field.placeholder) : undefined}
          onChange={(event) => onChange(field.key, event.target.value)}
          required={field.required}
          disabled={disabled}
        />
      </label>
    );
  }

  if (field.type === "select") {
    return (
      <label className="form-field" htmlFor={id}>
        <span>{t(field.label)}</span>
        <select id={id} value={String(value ?? "")} onChange={(event) => onChange(field.key, event.target.value)} disabled={disabled}>
          {(field.options ?? []).map((option) => (
            <option key={option} value={option}>
              {displayLabel(option, t)}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (field.type === "checkbox") {
    return (
      <label className="checkbox-field" htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(event) => onChange(field.key, event.target.checked)}
          disabled={disabled}
        />
        <span>{t(field.label)}</span>
      </label>
    );
  }

  return (
    <label className="form-field" htmlFor={id}>
      <span>{t(field.label)}</span>
      <input
        id={id}
        type={field.type}
        value={String(value ?? "")}
        placeholder={field.placeholder ? t(field.placeholder) : undefined}
        onChange={(event) => onChange(field.key, field.type === "number" ? Number(event.target.value) : event.target.value)}
        required={field.required}
        disabled={disabled}
      />
    </label>
  );
}

export function ConfigPage({ page, rows, onRowsChange, onNavigate, t }: ConfigPageProps) {
  const [query, setQuery] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formState, setFormState] = useState<FormState>(() => emptyForm(page.fields));
  const [lastSavedName, setLastSavedName] = useState<string | null>(null);
  const guidance = pageGuidance[page.route];
  const isReadOnly = page.mode === "read";

  const filteredRows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return rows;
    return rows.filter((row) => Object.values(row).some((value) => String(value).toLowerCase().includes(normalized)));
  }, [query, rows]);

  const openCreate = () => {
    if (isReadOnly) return;
    setEditingId(null);
    setFormState(emptyForm(page.fields));
    setModalOpen(true);
  };

  const openEdit = (row: EntityRow) => {
    setEditingId(row.id);
    setFormState({ ...row });
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingId(null);
  };

  const saveForm = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isReadOnly) {
      closeModal();
      return;
    }
    const nextRow: EntityRow = {
      id: editingId ?? createId(page.route),
      name: String(formState.name || page.modalTitle),
      status: String(formState.status || "draft"),
      owner: String(formState.owner || "待分配"),
      ...formState
    };

    if (editingId) {
      onRowsChange(rows.map((row) => (row.id === editingId ? nextRow : row)));
    } else {
      onRowsChange([nextRow, ...rows]);
    }
    setLastSavedName(nextRow.name);
    closeModal();
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">{t(page.eyebrow)}</p>
          <h2>{t(page.title)}</h2>
          <p className="description">{t(page.description)}</p>
        </div>
        <div className="page-actions">
          {!isReadOnly ? (
            <button type="button" className="primary-button" onClick={openCreate}>
              {t(page.primaryAction)}
            </button>
          ) : null}
        </div>
      </div>

      <div className="guidance-strip">
        <div>
          <strong>{t(guidance.goal)}</strong>
          <span>{t(guidance.primaryTask)}</span>
        </div>
        {guidance.nextRoute ? (
          <button type="button" className="secondary-button" onClick={() => onNavigate(guidance.nextRoute!)}>
            {t(guidance.nextLabel)}
          </button>
        ) : null}
      </div>

      {lastSavedName ? (
        <div className="next-step-card">
          <div>
            <strong>
              {t("已保存：")}
              {t(lastSavedName)}
            </strong>
            <span>{t("建议继续下一步，验证配置是否形成闭环。")}</span>
          </div>
          {guidance.nextRoute ? (
            <button type="button" className="primary-button" onClick={() => onNavigate(guidance.nextRoute!)}>
              {t(guidance.nextLabel)}
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="metric-grid">
        {page.metrics.map((metric) => (
          <article key={metric.label} className={`metric-card tone-${metric.tone}`}>
            <p>{t(metric.label)}</p>
            <strong>{t(metric.value)}</strong>
            <span>{t(metric.delta)}</span>
          </article>
        ))}
      </div>

      <div className="guardrail-strip">
        <strong>{t("控制边界")}</strong>
        <span>{t(page.guardrail)}</span>
      </div>

      <div className="panel">
        <div className="panel-toolbar">
            <div>
              <h3>{t("配置对象")}</h3>
              <p>
                {filteredRows.length} {t("条记录")}
                {isReadOnly ? `, ${t("当前页面只读观测")}` : `, ${t("保存仅更新本地 mock state")}`}
              </p>
            </div>
          <input
            className="search-input"
            type="search"
            placeholder={t("筛选对象、状态、负责人")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {page.columns.map((column) => (
                  <th key={column.key}>{t(column.label)}</th>
                ))}
                <th>{t("操作")}</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.length ? (
                filteredRows.map((row) => (
                  <tr key={row.id}>
                    {page.columns.map((column) => (
                      <td key={`${row.id}-${column.key}`}>{displayCell(row[column.key], column, t)}</td>
                    ))}
                    <td>
                      <button type="button" className="ghost-button" onClick={() => openEdit(row)}>
                        {isReadOnly ? t("查看") : t("编辑")}
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={page.columns.length + 1}>
                    <div className="empty-state">
                      <strong>{t(query ? "没有匹配记录" : "暂无配置对象")}</strong>
                      <span>{t(isReadOnly ? "当前观测页暂无可展示数据。" : "可以新增一个对象，或调整筛选条件后重试。")}</span>
                      {!isReadOnly ? (
                        <button type="button" className="secondary-button" onClick={openCreate}>
                          {t(page.primaryAction)}
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {modalOpen ? (
        <div className="modal-backdrop" role="presentation">
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
            <div className="modal-header">
              <div>
                <p className="eyebrow">{isReadOnly ? t("查看") : editingId ? t("编辑") : t("新增")}</p>
                <h3 id="modal-title">{t(page.modalTitle)}</h3>
              </div>
              <button type="button" className="icon-button" aria-label={t("关闭弹窗")} onClick={closeModal}>
                ×
              </button>
            </div>

            <form className="modal-form" onSubmit={saveForm}>
              {page.fields.map((field) => (
                <FormField
                  key={field.key}
                  field={field}
                  value={formState[field.key]}
                  onChange={(key, value) => setFormState((current) => ({ ...current, [key]: value }))}
                  t={t}
                  disabled={isReadOnly}
                />
              ))}
              <div className="modal-actions">
                <button type="button" className="secondary-button" onClick={closeModal}>
                  {isReadOnly ? t("关闭") : t("取消")}
                </button>
                {!isReadOnly ? (
                  <button type="submit" className="primary-button">
                    {t("保存到 mock state")}
                  </button>
                ) : null}
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </section>
  );
}
