import React from 'react'

function CompassMap({ profile }) {
  return (
    <div className="compass-map" aria-label="Your compass map">
      <div className="compass-cross vertical" /><div className="compass-cross horizontal" />
      <span className="compass-axis north">Evil is made</span><span className="compass-axis south">Evil simply is</span>
      <span className="compass-axis west">Given order</span><span className="compass-axis east">Self-authorship</span>
      {profile.points.map((point, index) => (
        <React.Fragment key={`${point.x}-${point.y}-${index}`}>
          <i className="film-dot" style={{ left: `${point.x}%`, top: `${point.y}%` }} />
          {point.label && <span className={`film-label ${point.align === 'left' ? 'left-label' : ''}`} style={{ left: `${point.x}%`, top: `${point.y}%` }}>{point.label}</span>}
        </React.Fragment>
      ))}
      <div className="you-halo" style={{ left: `${profile.position.x}%`, top: `${profile.position.y}%` }} />
      <i className="you-marker" style={{ left: `${profile.position.x}%`, top: `${profile.position.y}%` }} />
      <span className="you-label" style={{ left: `${profile.position.x}%`, top: `${profile.position.y}%` }}>You</span>
    </div>
  )
}

export default CompassMap
