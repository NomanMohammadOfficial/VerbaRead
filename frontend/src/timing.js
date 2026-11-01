const WORD_RE = /[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*/g

function normalizeWord(word) {
  return String(word || '')
    .toLowerCase()
    .replace(/\u0301/g, '')
    .replace(/ё/g, 'е')
}

export function cueWords(text) {
  const plain = String(text || '').replace(/\u0301/g, '')
  const matches = plain.match(WORD_RE) || []
  return matches.map(normalizeWord)
}

export function lessonWords(tokens) {
  const list = []
  ;(tokens || []).forEach((token, index) => {
    if (token?.kind === 'word') list.push({ index, word: normalizeWord(token.text) })
  })
  return list
}

function windowMatches(list, start, words) {
  if (start < 0 || start + words.length > list.length) return false
  for (let offset = 0; offset < words.length; offset += 1) {
    if (list[start + offset].word !== words[offset]) return false
  }
  return true
}

function buildIndex(list) {
  const index = new Map()
  list.forEach((item, position) => {
    const bucket = index.get(item.word)
    if (bucket) bucket.push(position)
    else index.set(item.word, [position])
  })
  return index
}

export function locateCue(list, index, words, cursor) {
  if (!words.length) return -1
  const bucket = index.get(words[0]) || []
  let ahead = -1
  let behind = -1
  bucket.forEach((position) => {
    if (!windowMatches(list, position, words)) return
    if (position >= cursor) {
      if (ahead < 0 || position < ahead) ahead = position
      return
    }
    if (position > behind) behind = position
  })
  if (ahead >= 0) return ahead
  return behind
}

function buildWeights(words, count) {
  const chars = []
  let total = 0
  for (let offset = 0; offset < count; offset += 1) {
    const word = words[Math.min(offset, words.length - 1)] || ''
    total += Math.max(1, word.length)
    chars.push(total)
  }
  return { chars, total }
}

export function buildMediaMap(tokens, cues) {
  const list = lessonWords(tokens)
  const slots = list.map((item) => item.index)
  const source = Array.isArray(cues) ? cues : []
  if (!list.length || !source.length) return { ranges: [], slots }

  const index = buildIndex(list)
  const ranges = []
  let cursor = 0

  source.forEach((cue) => {
    const words = cueWords(cue?.text)
    if (!words.length) return
    let at = locateCue(list, index, words, cursor)
    if (at < 0) at = Math.min(cursor, list.length - 1)
    const count = Math.min(words.length, list.length - at)
    const last = at + count - 1
    const start = Number(cue.start) || 0
    const duration = Number(cue.duration) || 0
    const { chars, total } = buildWeights(words, count)
    ranges.push({
      start,
      end: Math.max(start + 0.2, start + duration),
      first: at,
      last,
      count,
      chars,
      totalChars: total,
    })
    cursor = Math.max(cursor, last + 1)
  })

  ranges.forEach((range, position) => {
    const next = ranges[position + 1]
    if (next && next.start > range.start) range.end = Math.min(range.end, next.start)
    range.end = Math.max(range.start + 0.2, range.end)
  })

  return { ranges, slots }
}

export function localIndex(range, frac) {
  const count = Math.max(1, range.count || 0)
  if (range.totalChars > 0 && range.chars?.length) {
    const target = frac * range.totalChars
    for (let offset = 0; offset < range.chars.length; offset += 1) {
      if (target < range.chars[offset]) return Math.min(count - 1, offset)
    }
    return count - 1
  }
  return Math.min(count - 1, Math.floor(frac * count))
}

export function ordinalAtTime(ranges, time) {
  if (!ranges?.length) return null
  let range = ranges.find((item) => time >= item.start && time < item.end)
  if (!range) {
    let best = null
    let bestGap = Infinity
    ranges.forEach((item) => {
      const gap = time < item.start ? item.start - time : time - item.end
      if (gap < bestGap) {
        bestGap = gap
        best = item
      }
    })
    if (!best || bestGap > 3) return null
    range = best
  }
  const span = Math.max(0.2, range.end - range.start)
  const frac = Math.max(0, Math.min(0.999, (time - range.start) / span))
  return range.first + localIndex(range, frac)
}

export function wordTiming(ranges, ordinal) {
  if (!ranges?.length) return null
  const range = ranges.find((item) => ordinal >= item.first && ordinal <= item.last)
  if (!range) return null
  const span = Math.max(0.25, range.end - range.start)
  const count = Math.max(1, range.count)
  const local = Math.max(0, Math.min(count - 1, ordinal - range.first))
  let start
  let end
  if (range.totalChars > 0 && range.chars?.length) {
    const before = local > 0 ? range.chars[local - 1] : 0
    const after = range.chars[local] || before + 1
    start = range.start + span * (before / range.totalChars)
    end = range.start + span * (after / range.totalChars)
  } else {
    start = range.start + span * (local / count)
    end = range.start + span * ((local + 1) / count)
  }
  return { start, end: Math.max(start + 0.12, end) }
}
