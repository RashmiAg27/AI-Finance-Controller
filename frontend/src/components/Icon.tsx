/**
 * Flat pictograms in the Office 2007 idiom: solid shapes, one or two colours,
 * legible at 16px. Drawn inline rather than pulled from an icon font so a
 * ribbon button renders identically at 16 and 32 without a webfont round trip.
 */
export type IconName =
  | 'recon'
  | 'tax'
  | 'rules'
  | 'forecast'
  | 'exception'
  | 'run'
  | 'runAll'
  | 'edit'
  | 'save'
  | 'refresh'
  | 'client'
  | 'log'
  | 'connect'
  | 'folder'
  | 'mail'
  | 'server'
  | 'cloud'
  | 'close'
  | 'agent'
  | 'undo'
  | 'report';

const PATHS: Record<IconName, (s: number) => React.ReactNode> = {
  recon: (s) => (
    <g>
      <rect x={s * 0.08} y={s * 0.16} width={s * 0.36} height={s * 0.68} fill="#4a7ab5" />
      <rect x={s * 0.56} y={s * 0.16} width={s * 0.36} height={s * 0.68} fill="#8fb4dd" />
      <path
        d={`M${s * 0.3} ${s * 0.5} L${s * 0.7} ${s * 0.5}`}
        stroke="#2e7d32"
        strokeWidth={s * 0.12}
      />
    </g>
  ),
  tax: (s) => (
    <g>
      <rect x={s * 0.16} y={s * 0.08} width={s * 0.62} height={s * 0.84} fill="#fff" stroke="#4a7ab5" strokeWidth={s * 0.07} />
      <rect x={s * 0.28} y={s * 0.26} width={s * 0.38} height={s * 0.08} fill="#4a7ab5" />
      <rect x={s * 0.28} y={s * 0.44} width={s * 0.38} height={s * 0.08} fill="#8fb4dd" />
      <text x={s * 0.3} y={s * 0.82} fontSize={s * 0.34} fill="#a86400" fontFamily="Segoe UI" fontWeight="700">
        %
      </text>
    </g>
  ),
  rules: (s) => (
    <g>
      <rect x={s * 0.08} y={s * 0.2} width={s * 0.3} height={s * 0.16} fill="#4a7ab5" />
      <rect x={s * 0.08} y={s * 0.62} width={s * 0.3} height={s * 0.16} fill="#4a7ab5" />
      <rect x={s * 0.62} y={s * 0.2} width={s * 0.3} height={s * 0.16} fill="#8fb4dd" />
      <rect x={s * 0.62} y={s * 0.62} width={s * 0.3} height={s * 0.16} fill="#8fb4dd" />
      <path d={`M${s * 0.38} ${s * 0.28} L${s * 0.62} ${s * 0.28}`} stroke="#2e7d32" strokeWidth={s * 0.08} />
      <path d={`M${s * 0.38} ${s * 0.7} L${s * 0.62} ${s * 0.3}`} stroke="#a86400" strokeWidth={s * 0.08} />
    </g>
  ),
  forecast: (s) => (
    <g>
      <path d={`M${s * 0.1} ${s * 0.88} L${s * 0.1} ${s * 0.1}`} stroke="#7a8899" strokeWidth={s * 0.07} />
      <path d={`M${s * 0.1} ${s * 0.88} L${s * 0.92} ${s * 0.88}`} stroke="#7a8899" strokeWidth={s * 0.07} />
      <path
        d={`M${s * 0.16} ${s * 0.7} L${s * 0.4} ${s * 0.46} L${s * 0.58} ${s * 0.58} L${s * 0.86} ${s * 0.2}`}
        stroke="#2e7d32"
        strokeWidth={s * 0.1}
        fill="none"
      />
    </g>
  ),
  exception: (s) => (
    <g>
      <path d={`M${s * 0.5} ${s * 0.08} L${s * 0.94} ${s * 0.86} L${s * 0.06} ${s * 0.86} Z`} fill="#e0a12c" stroke="#8a5100" strokeWidth={s * 0.05} />
      <rect x={s * 0.44} y={s * 0.36} width={s * 0.12} height={s * 0.26} fill="#5a3407" />
      <rect x={s * 0.44} y={s * 0.68} width={s * 0.12} height={s * 0.1} fill="#5a3407" />
    </g>
  ),
  run: (s) => (
    <g>
      <circle cx={s * 0.5} cy={s * 0.5} r={s * 0.42} fill="#4f9e3c" />
      <path d={`M${s * 0.4} ${s * 0.28} L${s * 0.74} ${s * 0.5} L${s * 0.4} ${s * 0.72} Z`} fill="#fff" />
    </g>
  ),
  runAll: (s) => (
    <g>
      <circle cx={s * 0.5} cy={s * 0.5} r={s * 0.42} fill="#4f9e3c" />
      <path d={`M${s * 0.28} ${s * 0.3} L${s * 0.55} ${s * 0.5} L${s * 0.28} ${s * 0.7} Z`} fill="#fff" />
      <path d={`M${s * 0.54} ${s * 0.3} L${s * 0.81} ${s * 0.5} L${s * 0.54} ${s * 0.7} Z`} fill="#fff" />
    </g>
  ),
  edit: (s) => (
    <g>
      <path d={`M${s * 0.14} ${s * 0.72} L${s * 0.66} ${s * 0.2} L${s * 0.82} ${s * 0.36} L${s * 0.3} ${s * 0.88} L${s * 0.1} ${s * 0.92} Z`} fill="#e0c06a" stroke="#8a6a1c" strokeWidth={s * 0.05} />
      <path d={`M${s * 0.66} ${s * 0.2} L${s * 0.8} ${s * 0.06} L${s * 0.94} ${s * 0.22} L${s * 0.82} ${s * 0.36} Z`} fill="#8fb4dd" stroke="#2c4d75" strokeWidth={s * 0.05} />
    </g>
  ),
  save: (s) => (
    <g>
      <rect x={s * 0.1} y={s * 0.1} width={s * 0.8} height={s * 0.8} fill="#4a7ab5" />
      <rect x={s * 0.26} y={s * 0.1} width={s * 0.48} height={s * 0.32} fill="#e9f0f9" />
      <rect x={s * 0.22} y={s * 0.54} width={s * 0.56} height={s * 0.36} fill="#fff" />
      <rect x={s * 0.56} y={s * 0.14} width={s * 0.12} height={s * 0.22} fill="#2c4d75" />
    </g>
  ),
  refresh: (s) => (
    <g>
      <path
        d={`M${s * 0.82} ${s * 0.5} a${s * 0.32} ${s * 0.32} 0 1 1 -${s * 0.12} -${s * 0.22}`}
        fill="none"
        stroke="#2e7d32"
        strokeWidth={s * 0.12}
      />
      <path d={`M${s * 0.56} ${s * 0.12} L${s * 0.78} ${s * 0.3} L${s * 0.54} ${s * 0.38} Z`} fill="#2e7d32" />
    </g>
  ),
  client: (s) => (
    <g>
      <circle cx={s * 0.5} cy={s * 0.32} r={s * 0.2} fill="#4a7ab5" />
      <path d={`M${s * 0.14} ${s * 0.9} a${s * 0.36} ${s * 0.32} 0 0 1 ${s * 0.72} 0 Z`} fill="#8fb4dd" />
    </g>
  ),
  log: (s) => (
    <g>
      <rect x={s * 0.14} y={s * 0.08} width={s * 0.72} height={s * 0.84} fill="#fff" stroke="#7a8899" strokeWidth={s * 0.06} />
      <rect x={s * 0.26} y={s * 0.26} width={s * 0.48} height={s * 0.07} fill="#4a7ab5" />
      <rect x={s * 0.26} y={s * 0.44} width={s * 0.48} height={s * 0.07} fill="#8fb4dd" />
      <rect x={s * 0.26} y={s * 0.62} width={s * 0.32} height={s * 0.07} fill="#8fb4dd" />
    </g>
  ),
  connect: (s) => (
    <g>
      <circle cx={s * 0.24} cy={s * 0.5} r={s * 0.16} fill="#4a7ab5" />
      <circle cx={s * 0.76} cy={s * 0.5} r={s * 0.16} fill="#4f9e3c" />
      <path d={`M${s * 0.36} ${s * 0.5} L${s * 0.64} ${s * 0.5}`} stroke="#2c4d75" strokeWidth={s * 0.1} />
    </g>
  ),
  folder: (s) => (
    <g>
      <path d={`M${s * 0.06} ${s * 0.24} h${s * 0.32} l${s * 0.1} ${s * 0.12} h${s * 0.46} v${s * 0.5} h-${s * 0.88} Z`} fill="#e8c06a" stroke="#a07a1c" strokeWidth={s * 0.05} />
    </g>
  ),
  mail: (s) => (
    <g>
      <rect x={s * 0.06} y={s * 0.24} width={s * 0.88} height={s * 0.54} fill="#fff" stroke="#4a7ab5" strokeWidth={s * 0.06} />
      <path d={`M${s * 0.06} ${s * 0.24} L${s * 0.5} ${s * 0.58} L${s * 0.94} ${s * 0.24}`} fill="none" stroke="#4a7ab5" strokeWidth={s * 0.06} />
    </g>
  ),
  server: (s) => (
    <g>
      <rect x={s * 0.12} y={s * 0.14} width={s * 0.76} height={s * 0.26} fill="#8fb4dd" stroke="#2c4d75" strokeWidth={s * 0.05} />
      <rect x={s * 0.12} y={s * 0.58} width={s * 0.76} height={s * 0.26} fill="#8fb4dd" stroke="#2c4d75" strokeWidth={s * 0.05} />
      <circle cx={s * 0.26} cy={s * 0.27} r={s * 0.05} fill="#4f9e3c" />
      <circle cx={s * 0.26} cy={s * 0.71} r={s * 0.05} fill="#4f9e3c" />
    </g>
  ),
  cloud: (s) => (
    <g>
      <path
        d={`M${s * 0.24} ${s * 0.74} a${s * 0.17} ${s * 0.17} 0 0 1 0 -${s * 0.34} a${s * 0.24} ${s * 0.24} 0 0 1 ${s * 0.46} -${s * 0.06} a${s * 0.2} ${s * 0.2} 0 0 1 ${s * 0.06} ${s * 0.4} Z`}
        fill="#8fb4dd"
        stroke="#2c4d75"
        strokeWidth={s * 0.05}
      />
    </g>
  ),
  close: (s) => (
    <g stroke="#8c1620" strokeWidth={s * 0.14} strokeLinecap="round">
      <path d={`M${s * 0.24} ${s * 0.24} L${s * 0.76} ${s * 0.76}`} />
      <path d={`M${s * 0.76} ${s * 0.24} L${s * 0.24} ${s * 0.76}`} />
    </g>
  ),
  agent: (s) => (
    <g>
      <rect x={s * 0.16} y={s * 0.24} width={s * 0.68} height={s * 0.5} rx={s * 0.08} fill="#4a7ab5" />
      <circle cx={s * 0.36} cy={s * 0.46} r={s * 0.07} fill="#fff" />
      <circle cx={s * 0.64} cy={s * 0.46} r={s * 0.07} fill="#fff" />
      <path d={`M${s * 0.3} ${s * 0.74} L${s * 0.3} ${s * 0.92} L${s * 0.48} ${s * 0.74} Z`} fill="#4a7ab5" />
      <path d={`M${s * 0.5} ${s * 0.1} L${s * 0.5} ${s * 0.24}`} stroke="#2c4d75" strokeWidth={s * 0.06} />
    </g>
  ),
  undo: (s) => (
    <g>
      <path
        d={`M${s * 0.2} ${s * 0.5} a${s * 0.3} ${s * 0.3} 0 1 0 ${s * 0.12} -${s * 0.22}`}
        fill="none"
        stroke="#a86400"
        strokeWidth={s * 0.12}
      />
      <path d={`M${s * 0.42} ${s * 0.14} L${s * 0.2} ${s * 0.3} L${s * 0.44} ${s * 0.4} Z`} fill="#a86400" />
    </g>
  ),
  report: (s) => (
    <g>
      <rect x={s * 0.14} y={s * 0.08} width={s * 0.72} height={s * 0.84} fill="#fff" stroke="#4a7ab5" strokeWidth={s * 0.06} />
      <rect x={s * 0.26} y={s * 0.58} width={s * 0.12} height={s * 0.24} fill="#4a7ab5" />
      <rect x={s * 0.44} y={s * 0.42} width={s * 0.12} height={s * 0.4} fill="#4f9e3c" />
      <rect x={s * 0.62} y={s * 0.28} width={s * 0.12} height={s * 0.54} fill="#e0a12c" />
    </g>
  ),
};

export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" focusable="false">
      {PATHS[name](size)}
    </svg>
  );
}
