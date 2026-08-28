export function Mark() {
  return (
    <svg className="mark" viewBox="0 0 22 22" fill="none" aria-hidden="true">
      <circle cx="5" cy="11" r="2.6" fill="#c8f24a" />
      <circle cx="17" cy="11" r="2.6" stroke="#c8f24a" strokeWidth="1.6" />
      <path d="M7.8 11h6.4" stroke="#c8f24a" strokeWidth="1.4" />
    </svg>
  )
}

export function IconBoard() {
  return (
    <svg className="ico" viewBox="0 0 16 16" fill="none">
      <rect x="1.5" y="1.5" width="5.5" height="5.5" stroke="currentColor" />
      <rect x="9" y="1.5" width="5.5" height="3.5" stroke="currentColor" />
      <rect x="9" y="7" width="5.5" height="7.5" stroke="currentColor" />
      <rect x="1.5" y="9" width="5.5" height="5.5" stroke="currentColor" />
    </svg>
  )
}

export function IconRelays() {
  return (
    <svg className="ico" viewBox="0 0 16 16" fill="none">
      <path d="M3 4h6M3 8h10M3 12h6" stroke="currentColor" />
      <circle cx="12" cy="4" r="1.4" stroke="currentColor" />
      <circle cx="12" cy="12" r="1.4" stroke="currentColor" />
    </svg>
  )
}

export function IconActivity() {
  return (
    <svg className="ico" viewBox="0 0 16 16" fill="none">
      <path d="M1 12h3l2-7 3 10 2-6h4" stroke="currentColor" />
    </svg>
  )
}

export function IconGear() {
  return (
    <svg className="ico" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="2.2" stroke="currentColor" />
      <path d="M8 1.6v2M8 12.4v2M1.6 8h2M12.4 8h2M3.2 3.2l1.4 1.4M11.4 11.4l1.4 1.4M12.8 3.2l-1.4 1.4M4.6 11.4l-1.4 1.4" stroke="currentColor" />
    </svg>
  )
}

export function Schema() {
  return (
    <svg className="schema" viewBox="0 0 180 88" fill="none" aria-hidden="true">
      <rect x="8" y="8" width="72" height="28" stroke="#c8f24a" strokeOpacity="0.7" />
      <rect x="100" y="52" width="72" height="28" stroke="#c8f24a" />
      <path d="M44 36v14h56v2" stroke="#c8f24a" />
      <circle cx="44" cy="50" r="3" fill="#c8f24a" />
      <text x="18" y="26" fill="#c8f24a" fontSize="9" fontFamily="IBM Plex Mono, monospace">
        ORIGIN
      </text>
      <text x="114" y="70" fill="#c8f24a" fontSize="9" fontFamily="IBM Plex Mono, monospace">
        DEST
      </text>
    </svg>
  )
}
