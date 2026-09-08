import React from 'react'

// Every figure the atlas quotes comes from the `findings` table with its own
// provenance, rather than being typed into the page. A number that changes
// should change the page, and a number that goes missing should say so: a
// missing finding renders as an em dash rather than as "undefined" or, worse,
// as a stale literal nobody notices is stale.
//
// `display` when the raw number reads badly, the value otherwise.
export default function Fig({ from, name, suffix = '' }) {
  const f = from?.[name]
  if (!f) return <b>—</b>
  return (
    <b title={[f.note, f.source].filter(Boolean).join(' · ')}>
      {f.display ?? f.value}{suffix}
    </b>
  )
}
