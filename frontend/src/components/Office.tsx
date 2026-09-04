import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Icon, type IconName } from './Icon';

/** Hover-intent delay before a ribbon tooltip appears -- long enough that a
 *  cursor passing over several buttons on its way elsewhere never triggers
 *  one. Keyboard focus skips the delay: a tab landing on the button is
 *  already a deliberate stop, not a pass-through. */
const TOOLTIP_DELAY_MS = 500;

/* --------------------------------------------------------------------------
   Ribbon
   -------------------------------------------------------------------------- */

export function RibbonGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rgroup">
      <div className="rgroup__items">{children}</div>
      <div className="rgroup__label">{label}</div>
    </div>
  );
}

export function RibbonStack({ children }: { children: ReactNode }) {
  return <div className="rgroup__stack">{children}</div>;
}

export function RibbonButton({
  icon,
  label,
  onClick,
  disabled,
  small,
  title,
  description,
}: {
  icon: IconName;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  small?: boolean;
  title?: string;
  /** A one-to-two-line explanation shown as a native-looking tooltip on
   *  hover (after a short delay) or keyboard focus (immediately). Purely
   *  informational -- it never intercepts the click. Falls back to a plain
   *  browser title tooltip when omitted. */
  description?: string;
}) {
  const [tipVisible, setTipVisible] = useState(false);
  const [tipPos, setTipPos] = useState<{ top: number; left: number } | null>(null);
  const timerRef = useRef<number | undefined>(undefined);
  const anchorRef = useRef<HTMLSpanElement>(null);
  const tipId = useId();

  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  // The ribbon clips overflow to hold a fixed height (.ribbon__body), which
  // would slice off a tooltip hanging below it -- so the tooltip itself is
  // portaled to <body> and positioned from the anchor's live screen
  // coordinates, rather than laid out in normal flow inside the ribbon. The
  // horizontal center is clamped so the leftmost/rightmost ribbon buttons
  // don't push it past the viewport edge (it renders centered -- see the
  // matching `transform: translateX(-50%)` in .rbtn-tooltip).
  const reveal = (show: () => void) => {
    const rect = anchorRef.current?.getBoundingClientRect();
    if (rect) {
      const halfWidth = 120; // half of .rbtn-tooltip's 240px width
      const margin = 8;
      const centerX = rect.left + rect.width / 2;
      const clampedX = Math.min(
        Math.max(centerX, halfWidth + margin),
        window.innerWidth - halfWidth - margin,
      );
      setTipPos({ top: rect.bottom + 6, left: clampedX });
    }
    show();
  };
  const showAfterDelay = () => {
    window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => reveal(() => setTipVisible(true)), TOOLTIP_DELAY_MS);
  };
  const showNow = () => {
    window.clearTimeout(timerRef.current);
    reveal(() => setTipVisible(true));
  };
  const hide = () => {
    window.clearTimeout(timerRef.current);
    setTipVisible(false);
  };

  return (
    <span
      className="rbtn-wrap"
      ref={anchorRef}
      onMouseEnter={description ? showAfterDelay : undefined}
      onMouseLeave={description ? hide : undefined}
    >
      <button
        type="button"
        className={small ? 'rbtn rbtn--small' : 'rbtn'}
        onClick={onClick}
        disabled={disabled}
        title={description ? undefined : (title ?? label)}
        aria-describedby={description && tipVisible ? tipId : undefined}
        onFocus={description ? showNow : undefined}
        onBlur={description ? hide : undefined}
      >
        <Icon name={icon} size={small ? 16 : 32} />
        <span className="rbtn__label">{label}</span>
      </button>
      {description && tipVisible && tipPos &&
        createPortal(
          <span
            className="rbtn-tooltip"
            role="tooltip"
            id={tipId}
            style={{ top: tipPos.top, left: tipPos.left }}
          >
            <span className="rbtn-tooltip__title">{label}</span>
            <span className="rbtn-tooltip__desc">{description}</span>
          </span>,
          document.body,
        )}
    </span>
  );
}

/* --------------------------------------------------------------------------
   Panes
   -------------------------------------------------------------------------- */

export function Pane({
  title,
  hint,
  children,
  defaultOpen = true,
  flush,
  actions,
}: {
  title: string;
  hint?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  flush?: boolean;
  actions?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="pane">
      <header
        className="pane__header"
        onClick={() => setOpen((v) => !v)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setOpen((v) => !v);
          }
        }}
      >
        <span className="pane__twisty">{open ? '▼' : '►'}</span>
        <span>{title}</span>
        {hint && <span className="pane__hint">{hint}</span>}
        <span className="blotter__spacer" />
        {actions && (
          <span onClick={(e) => e.stopPropagation()} role="presentation">
            {actions}
          </span>
        )}
      </header>
      {open && <div className={flush ? 'pane__body pane__body--flush' : 'pane__body'}>{children}</div>}
    </section>
  );
}

/* --------------------------------------------------------------------------
   Dialog
   -------------------------------------------------------------------------- */

export function Dialog({
  title,
  onClose,
  children,
  footer,
  width,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" style={width ? { width } : undefined} role="dialog" aria-label={title}>
        <div className="dialog__title">
          <span className="blotter__spacer">{title}</span>
          <button type="button" className="doctab__close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="dialog__body">{children}</div>
        {footer && <div className="dialog__footer">{footer}</div>}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Fields
   -------------------------------------------------------------------------- */

export function Field({
  label,
  children,
  note,
}: {
  label: string;
  children: ReactNode;
  note?: ReactNode;
}) {
  const id = useId();
  return (
    <>
      <div className="field">
        <label htmlFor={id}>{label}</label>
        <span className="field__control">{children}</span>
      </div>
      {note && <div className="field__note">{note}</div>}
    </>
  );
}

export function TextField({
  value,
  onChange,
  placeholder,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <input
      type="text"
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function NumberField({
  value,
  onChange,
  step = 'any',
  disabled,
}: {
  value: number;
  onChange: (v: number) => void;
  step?: string | number;
  disabled?: boolean;
}) {
  return (
    <input
      type="number"
      step={step}
      value={Number.isFinite(value) ? value : 0}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value === '' ? 0 : Number(e.target.value))}
    />
  );
}

export function SelectField({
  value,
  options,
  onChange,
  disabled,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <select value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/* --------------------------------------------------------------------------
   Status
   -------------------------------------------------------------------------- */

const BADGE_TONE: Record<string, string> = {
  COMPLETED: 'ok',
  CLOSED: 'ok',
  SUCCESS: 'ok',
  OK: 'ok',
  VERIFIED: 'ok',
  RUNNING: 'running',
  DATA_AVAILABLE: 'running',
  AWAITING_DATA: 'warn',
  EMPTY: 'warn',
  WARN: 'warn',
  NOT_VERIFIED: 'warn',
  PROTOTYPE_ASSUMPTION: 'warn',
  FAILED: 'error',
  ERROR: 'error',
  DISABLED: 'idle',
};

export function Badge({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="muted">—</span>;
  const tone = BADGE_TONE[value] ?? 'idle';
  return <span className={`badge badge--${tone}`}>{value.replace(/_/g, ' ')}</span>;
}

export function Progress({ pct }: { pct: number }) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <div className="progress" title={`${clamped}%`}>
      <div className="progress__fill" style={{ width: `${clamped}%` }} />
      <div className="progress__text">{clamped}%</div>
    </div>
  );
}

export function Kpi({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="kpi">
      <div className="kpi__label">{label}</div>
      <div className="kpi__value">{value}</div>
      {note && <div className="kpi__note">{note}</div>}
    </div>
  );
}

export function Callout({
  tone = 'info',
  children,
}: {
  tone?: 'info' | 'warn' | 'error';
  children: ReactNode;
}) {
  const cls = tone === 'info' ? 'callout' : `callout callout--${tone}`;
  return <div className={cls}>{children}</div>;
}

/* --------------------------------------------------------------------------
   Grid
   -------------------------------------------------------------------------- */

export function Grid({
  columns,
  children,
  empty,
  maxHeight,
}: {
  columns: { key: string; label: string; numeric?: boolean; width?: number }[];
  children: ReactNode;
  empty?: string;
  maxHeight?: number;
}) {
  const rows = Array.isArray(children) ? children.flat() : children;
  const isEmpty = Array.isArray(rows) ? rows.filter(Boolean).length === 0 : !rows;
  return (
    <div className="grid-wrap" style={maxHeight ? { maxHeight } : undefined}>
      <table className="grid">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.numeric ? 'num' : undefined} style={c.width ? { width: c.width } : undefined}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {isEmpty ? (
            <tr>
              <td colSpan={columns.length}>
                <div className="grid-empty">{empty ?? 'Nothing to show.'}</div>
              </td>
            </tr>
          ) : (
            rows
          )}
        </tbody>
      </table>
    </div>
  );
}
