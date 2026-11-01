import test from 'node:test'
import assert from 'node:assert/strict'
import { buildMediaMap, cueWords, lessonWords, ordinalAtTime, wordTiming } from './timing.js'

function tokensFrom(words) {
  const tokens = []
  words.forEach((word, position) => {
    if (position) tokens.push({ kind: 'other', text: ' ' })
    tokens.push({ kind: 'word', text: word })
  })
  return tokens
}

test('cueWords splits Russian words and normalises', () => {
  assert.deepEqual(cueWords('Ещё раз, привет!'), ['еще', 'раз', 'привет'])
  assert.deepEqual(cueWords('кни́га'), ['книга'])
  assert.deepEqual(cueWords(''), [])
})

test('lessonWords keeps token indexes and skips punctuation', () => {
  const tokens = tokensFrom(['Однажды', 'в', 'зимний'])
  assert.deepEqual(lessonWords(tokens), [
    { index: 0, word: 'однажды' },
    { index: 2, word: 'в' },
    { index: 4, word: 'зимний' },
  ])
})

test('cues align to their lesson positions', () => {
  const tokens = tokensFrom(['Однажды', 'в', 'зимний', 'вечер', 'я', 'вышел', 'из', 'дома'])
  const cues = [
    { text: 'Однажды в зимний', start: 0, duration: 2 },
    { text: 'вечер я вышел из', start: 2, duration: 2 },
    { text: 'дома', start: 4, duration: 1 },
  ]
  const { ranges, slots } = buildMediaMap(tokens, cues)
  assert.deepEqual(slots, [0, 2, 4, 6, 8, 10, 12, 14])
  assert.deepEqual(ranges.map((range) => range.first), [0, 3, 7])
  assert.deepEqual(ranges.map((range) => range.last), [2, 6, 7])
  assert.deepEqual(ranges.map((range) => range.count), [3, 4, 1])
})

test('a duplicated cue word does not shift later cues', () => {
  const tokens = tokensFrom(['Однажды', 'в', 'зимний', 'вечер', 'я', 'вышел', 'из', 'дома'])
  const cues = [
    { text: 'Однажды в зимний вечер вечер', start: 0, duration: 2 },
    { text: 'вечер я вышел из', start: 2, duration: 2 },
    { text: 'дома', start: 4, duration: 1 },
  ]
  const { ranges } = buildMediaMap(tokens, cues)
  assert.deepEqual(ranges.map((range) => range.first), [0, 3, 7])
})

test('missing cue text falls back without breaking order', () => {
  const tokens = tokensFrom(['Привет', 'мир'])
  const cues = [
    { text: 'Неизвестные слова', start: 0, duration: 1 },
    { text: 'мир', start: 1, duration: 1 },
  ]
  const { ranges } = buildMediaMap(tokens, cues)
  assert.deepEqual(ranges.map((range) => range.first), [0, 1])
  assert.equal(ranges[0].count, 2)
})

test('cue ends are clamped to the next cue start', () => {
  const tokens = tokensFrom(['раз', 'два'])
  const cues = [
    { text: 'раз', start: 0, duration: 5 },
    { text: 'два', start: 1, duration: 1 },
  ]
  const { ranges } = buildMediaMap(tokens, cues)
  assert.equal(ranges[0].end, 1)
})

test('buildMediaMap is empty without cues', () => {
  const tokens = tokensFrom(['раз'])
  assert.deepEqual(buildMediaMap(tokens, []), { ranges: [], slots: [0] })
  assert.deepEqual(buildMediaMap([], [{ text: 'раз', start: 0, duration: 1 }]), { ranges: [], slots: [] })
})

test('time maps to words by character weight', () => {
  const words = ['Я', 'купил', 'интересную', 'книгу']
  const { ranges } = buildMediaMap(tokensFrom(words), [
    { text: words.join(' '), start: 10, duration: 2 },
  ])
  assert.equal(ranges.length, 1)
  assert.deepEqual(ranges[0].chars, [1, 6, 16, 21])
  assert.equal(ordinalAtTime(ranges, 10), 0)
  assert.equal(ordinalAtTime(ranges, 10.1), 1)
  assert.equal(ordinalAtTime(ranges, 11), 2)
  assert.equal(ordinalAtTime(ranges, 11.9), 3)
  assert.equal(ordinalAtTime(ranges, 40), null)
})

test('wordTiming returns the span of one word', () => {
  const words = ['Я', 'купил', 'интересную', 'книгу']
  const { ranges } = buildMediaMap(tokensFrom(words), [
    { text: words.join(' '), start: 0, duration: 2 },
  ])
  const first = wordTiming(ranges, 0)
  const second = wordTiming(ranges, 1)
  const last = wordTiming(ranges, 3)
  assert.equal(first.start, 0)
  assert.ok(Math.abs(first.end - 0.12) < 0.001)
  assert.ok(Math.abs(second.start - (2 * 1) / 21) < 0.001)
  assert.ok(Math.abs(second.end - (2 * 6) / 21) < 0.001)
  assert.ok(Math.abs(last.start - (2 * 16) / 21) < 0.001)
  assert.ok(Math.abs(last.end - 2) < 0.001)
  assert.equal(wordTiming(ranges, 9), null)
})
