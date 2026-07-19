export default function WinrateRing({ winrate = 0, total = 0, size = 132, label = 'winrate' }) {
  const stroke = 10
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (winrate / 100) * circumference

  const color = total === 0 ? 'var(--text-tertiary)' : winrate >= 50 ? 'var(--long)' : 'var(--short)'

  return (
    <div className="ring-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke="var(--border)" strokeWidth={stroke}
        />
        {total > 0 && (
          <circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke={color} strokeWidth={stroke}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            style={{ transition: 'stroke-dashoffset 0.6s ease' }}
          />
        )}
      </svg>
      <div className="ring-center">
        <span className="ring-value">{total > 0 ? `${winrate}%` : '—'}</span>
        <span className="ring-label">{label}</span>
      </div>

      <style>{`
        .ring-wrap { position: relative; flex-shrink: 0; }
        .ring-center {
          position: absolute;
          inset: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 2px;
        }
        .ring-value {
          font-family: var(--font-mono);
          font-size: 26px;
          font-weight: 600;
          color: var(--text);
        }
        .ring-label {
          font-size: 11px;
          color: var(--text-tertiary);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
      `}</style>
    </div>
  )
}
