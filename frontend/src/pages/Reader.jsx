import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import { STATUSES } from '../statuses.js'
import { loadYouTubeApi } from '../yt.js'
import { buildMediaMap, ordinalAtTime, wordTiming } from '../timing.js'
import WordPanel from '../components/WordPanel.jsx'
import PhrasePanel from '../components/PhrasePanel.jsx'

const RATES = [0.7, 0.85, 1, 1.15, 1.3]
const CPS = 14

function pickRussianVoice() {
  if (typeof window === 'undefined' || !window.speechSynthesis) return null
  const voices = window.speechSynthesis.getVoices()
  const ruVoices = voices.filter((voice) => voice.lang?.toLowerCase().startsWith('ru'))
  if (!ruVoices.length) return null
  // Prioritize high-quality natural, neural, or online voices (e.g. Google русский, Microsoft Svetlana Natural)
  const natural = ruVoices.find((v) =>
    /natural|online|google|enhanced|premium|neural/i.test(v.name)
  )
  return natural || ruVoices[0]
}

export default function Reader({ lessonId, onBack, onChanged, notify }) {
  const [lesson, setLesson] = useState(null)
  const [tokens, setTokens] = useState([])
  const [lessonStats, setLessonStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [phrase, setPhrase] = useState(null)
  const [panelBusy, setPanelBusy] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [rate, setRate] = useState(1)
  const [mediaError, setMediaError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [dragRange, setDragRange] = useState(null)

  const tokensRef = useRef([])
  const textRef = useRef('')
  const playingRef = useRef(false)
  const rateRef = useRef(1)
  const charPosRef = useRef(0)
  const anchorRef = useRef({ char: 0, time: 0 })
  const activeElRef = useRef(null)
  const playerRef = useRef(null)
  const playerReadyRef = useRef(false)
  const hostRef = useRef(null)
  const audioRef = useRef(null)
  const cueRangesRef = useRef([])
  const wordIndicesRef = useRef([])
  const utterRef = useRef(null)
  const pausedRef = useRef(false)
  const pauseTimerRef = useRef(null)
  const ttsAudioRef = useRef(null)
  const dragRef = useRef({ active: false, start: -1, end: -1 })
  const suppressClickRef = useRef(false)

  const mode = lesson?.youtube_id ? 'youtube' : lesson?.audio_url ? 'audio' : 'tts'

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api
      .reader(lessonId)
      .then((data) => {
        if (cancelled) return
        setLesson(data.lesson)
        setTokens(data.tokens)
        setLessonStats(data.stats)
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [lessonId])

  useEffect(() => {
    tokensRef.current = tokens
  }, [tokens])

  useEffect(() => {
    textRef.current = lesson?.text || ''
  }, [lesson])

  useEffect(() => {
    playingRef.current = playing
  }, [playing])

  useEffect(() => {
    rateRef.current = rate
  }, [rate])

  const mediaMap = useMemo(() => buildMediaMap(tokens, lesson?.cues), [tokens, lesson])

  useEffect(() => {
    wordIndicesRef.current = mediaMap.slots
    cueRangesRef.current = mediaMap.ranges
  }, [mediaMap])

  const setActiveAtChar = useCallback((char) => {
    const list = tokensRef.current
    for (let index = 0; index < list.length; index += 1) {
      if (list[index].kind === 'word' && list[index].end >= char) {
        setActiveIndex(index)
        return
      }
    }
  }, [])

  const setActiveAtOrdinal = useCallback((ordinal) => {
    const slots = wordIndicesRef.current
    if (!slots.length) return
    const clamped = Math.max(0, Math.min(slots.length - 1, ordinal))
    setActiveIndex(slots[clamped])
  }, [])

  const highlightAtTime = useCallback(
    (time) => {
      const ordinal = ordinalAtTime(cueRangesRef.current, time)
      if (ordinal !== null) setActiveAtOrdinal(ordinal)
    },
    [setActiveAtOrdinal],
  )

  const stopSpeech = useCallback(() => {
    if (typeof window !== 'undefined' && window.speechSynthesis) window.speechSynthesis.cancel()
    if (ttsAudioRef.current) {
      ttsAudioRef.current.pause()
      ttsAudioRef.current = null
    }
    utterRef.current = null
    pausedRef.current = false
  }, [])

  const playTtsAudio = useCallback((text) => {
    if (!text || !text.trim()) return
    stopSpeech()
    const audio = new Audio(api.ttsUrl(text.trim()))
    ttsAudioRef.current = audio
    audio.play().catch(() => {
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel()
        const utterance = new SpeechSynthesisUtterance(text.trim())
        const voice = pickRussianVoice()
        if (voice) utterance.voice = voice
        utterance.lang = 'ru-RU'
        window.speechSynthesis.speak(utterance)
      }
    })
  }, [stopSpeech])

  const speakRange = useCallback(
    (from, to) => {
      if (typeof window === 'undefined' || !window.speechSynthesis) {
        setMediaError('This browser has no speech synthesis')
        return
      }
      const text = textRef.current
      if (!text) return
      const start = Math.max(0, Math.min(text.length, from))
      const end = Math.max(start, Math.min(text.length, to))
      if (end <= start) return
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(text.slice(start, end))
      const voice = pickRussianVoice()
      if (voice) utterance.voice = voice
      utterance.lang = 'ru-RU'
      utterance.rate = rateRef.current
      charPosRef.current = start
      anchorRef.current = { char: start, time: performance.now() }
      utterRef.current = utterance
      pausedRef.current = false
      utterance.onboundary = (event) => {
        if (utterRef.current !== utterance) return
        const char = start + (event.charIndex || 0)
        charPosRef.current = char
        anchorRef.current = { char, time: performance.now() }
        setActiveAtChar(char)
      }
      utterance.onend = () => {
        if (utterRef.current !== utterance) return
        utterRef.current = null
        pausedRef.current = false
        charPosRef.current = end
        playingRef.current = false
        setPlaying(false)
        setActiveIndex(-1)
      }
      utterance.onerror = (event) => {
        if (utterRef.current !== utterance) return
        utterRef.current = null
        pausedRef.current = false
        playingRef.current = false
        setPlaying(false)
        if (event.error === 'interrupted' || event.error === 'canceled') return
        setMediaError(event.error || 'Speech playback failed')
      }
      playingRef.current = true
      setPlaying(true)
      setMediaError('')
      window.speechSynthesis.speak(utterance)
    },
    [setActiveAtChar],
  )

  useEffect(() => {
    if (mode !== 'youtube' || !lesson?.youtube_id) return undefined
    const host = hostRef.current
    if (!host) return undefined
    let cancelled = false
    let player = null
    host.innerHTML = ''
    const mount = document.createElement('div')
    host.appendChild(mount)

    const onReady = () => {
      playerReadyRef.current = true
      setMediaError('')
    }
    const onStateChange = (event) => {
      const state = event?.data
      if (state === 1) {
        playingRef.current = true
        setPlaying(true)
        setMediaError('')
        return
      }
      if (state === 2 || state === 0) {
        playingRef.current = false
        setPlaying(false)
        if (state === 0) setActiveIndex(-1)
      }
    }

    loadYouTubeApi()
      .then((YT) => {
        if (cancelled || !mount.isConnected) return
        player = new YT.Player(mount, {
          videoId: lesson.youtube_id,
          playerVars: { rel: 0, modestbranding: 1 },
          events: { onReady, onStateChange },
        })
        playerRef.current = player
      })
      .catch((err) => {
        if (!cancelled) setMediaError(err.message)
      })

    return () => {
      cancelled = true
      playerReadyRef.current = false
      const current = player || playerRef.current
      try {
        current?.destroy?.()
      } catch {
        playerReadyRef.current = false
      }
      playerRef.current = null
      host.innerHTML = ''
    }
  }, [mode, lesson])

  useEffect(() => {
    if (!playing) return undefined
    if (mode === 'youtube') {
      const timer = setInterval(() => {
        const player = playerRef.current
        if (playerReadyRef.current && player?.getCurrentTime) {
          highlightAtTime(Number(player.getCurrentTime()) || 0)
        }
      }, 120)
      return () => clearInterval(timer)
    }
    if (mode === 'tts') {
      const timer = setInterval(() => {
        const anchor = anchorRef.current
        const elapsed = (performance.now() - anchor.time) / 1000
        const estimated = anchor.char + elapsed * CPS * rateRef.current
        if (estimated >= textRef.current.length) return
        setActiveAtChar(estimated)
      }, 160)
      return () => clearInterval(timer)
    }
    return undefined
  }, [playing, mode, highlightAtTime, setActiveAtChar])

  useEffect(() => {
    if (!playing || activeIndex < 0) return
    const textContainer = document.querySelector('.reader-text.scrollable')
    if (textContainer && activeElRef.current) {
      const containerRect = textContainer.getBoundingClientRect()
      const elementRect = activeElRef.current.getBoundingClientRect()

      // Only scroll if element is outside the visible area
      if (elementRect.top < containerRect.top || elementRect.bottom > containerRect.bottom) {
        activeElRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' })
      }
    }
  }, [activeIndex, playing])

  useEffect(() => {
    return () => {
      if (pauseTimerRef.current) clearTimeout(pauseTimerRef.current)
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel()
      }
    }
  }, [])

  function haltAudio() {
    if (pauseTimerRef.current) {
      clearTimeout(pauseTimerRef.current)
      pauseTimerRef.current = null
    }
    if (mode === 'youtube') {
      const player = playerRef.current
      if (playerReadyRef.current && player?.pauseVideo) player.pauseVideo()
    } else if (mode === 'audio') {
      audioRef.current?.pause()
    } else {
      stopSpeech()
    }
    playingRef.current = false
    setPlaying(false)
  }

  const play = useCallback(() => {
    setMediaError('')
    if (mode === 'youtube') {
      const player = playerRef.current
      if (!playerReadyRef.current || !player?.playVideo) {
        setMediaError('The YouTube player is not ready yet')
        return
      }
      player.playVideo()
      return
    }
    if (mode === 'audio') {
      const audio = audioRef.current
      if (!audio) return
      audio.play().catch((err) => setMediaError(err.message || 'Could not play the audio'))
      return
    }
    const synth = typeof window !== 'undefined' ? window.speechSynthesis : null
    if (!synth) {
      setMediaError('This browser has no speech synthesis')
      return
    }
    if (utterRef.current && pausedRef.current) {
      pausedRef.current = false
      anchorRef.current = { char: charPosRef.current, time: performance.now() }
      playingRef.current = true
      setPlaying(true)
      synth.resume()
      return
    }
    const text = textRef.current
    const from = charPosRef.current >= text.length ? 0 : charPosRef.current
    speakRange(from, text.length)
  }, [mode, speakRange])

  function pause() {
    if (mode === 'youtube') {
      const player = playerRef.current
      if (playerReadyRef.current && player?.pauseVideo) player.pauseVideo()
      return
    }
    if (mode === 'audio') {
      audioRef.current?.pause()
      return
    }
    if (!playingRef.current) return
    pausedRef.current = true
    if (typeof window !== 'undefined' && window.speechSynthesis) window.speechSynthesis.pause()
    playingRef.current = false
    setPlaying(false)
  }

  function restart() {
    setMediaError('')
    if (mode === 'youtube') {
      const player = playerRef.current
      if (!playerReadyRef.current || !player?.seekTo) {
        setMediaError('The YouTube player is not ready yet')
        return
      }
      player.seekTo(0, true)
      player.playVideo()
      return
    }
    if (mode === 'audio') {
      const audio = audioRef.current
      if (!audio) return
      audio.currentTime = 0
      audio.play().catch((err) => setMediaError(err.message || 'Could not play the audio'))
      return
    }
    charPosRef.current = 0
    pausedRef.current = false
    speakRange(0, textRef.current.length)
  }

  function changeRate(value) {
    setRate(value)
    rateRef.current = value
    if (mode === 'youtube') {
      const player = playerRef.current
      if (playerReadyRef.current && player?.setPlaybackRate) player.setPlaybackRate(value)
      return
    }
    if (mode === 'audio') {
      if (audioRef.current) audioRef.current.playbackRate = value
      return
    }
    if (playingRef.current) speakRange(charPosRef.current, textRef.current.length)
  }

  function playWord(index) {
    const token = tokensRef.current[index]
    if (!token) return
    haltAudio()
    setMediaError('')
    if (mode === 'tts') {
      playTtsAudio(token.text)
      return
    }
    const ordinal = wordIndicesRef.current.indexOf(index)
    const timing = wordTiming(cueRangesRef.current, ordinal)
    if (!timing) {
      setMediaError('No timed audio for this word')
      return
    }
    const until = Math.max(timing.start + 0.15, Math.min(timing.end, timing.start + 0.9))
    const duration = ((until - timing.start) / (rateRef.current || 1)) * 1000
    setActiveAtOrdinal(ordinal)
    if (mode === 'youtube') {
      const player = playerRef.current
      if (!playerReadyRef.current || !player?.seekTo) {
        setMediaError('The YouTube player is not ready yet')
        return
      }
      player.seekTo(timing.start, true)
      player.playVideo()
      setPlaying(true)
      playingRef.current = true
      pauseTimerRef.current = setTimeout(() => {
        pauseTimerRef.current = null
        try {
          player.pauseVideo()
        } catch {
          setMediaError('Could not play the video')
        }
      }, duration)
      return
    }
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = timing.start
    audio.play().catch((err) => setMediaError(err.message || 'Could not play the audio'))
    pauseTimerRef.current = setTimeout(() => {
      pauseTimerRef.current = null
      audio.pause()
    }, duration)
  }

  function beginDrag(index) {
    dragRef.current = { active: true, start: index, end: index }
    suppressClickRef.current = false
    setDragging(true)
    setDragRange({ first: index, last: index })
  }

  function extendDrag(index) {
    const drag = dragRef.current
    if (!drag.active || index < 0 || drag.end === index) return
    drag.end = index
    setDragRange({ first: Math.min(drag.start, index), last: Math.max(drag.start, index) })
  }

  function finishDrag() {
    const drag = dragRef.current
    if (!drag.active) return
    drag.active = false
    setDragging(false)
    setDragRange(null)
    const first = Math.min(drag.start, drag.end)
    const last = Math.max(drag.start, drag.end)
    dragRef.current = { active: false, start: -1, end: -1 }
    if (first === last || first < 0) return
    const from = tokensRef.current[first]
    const to = tokensRef.current[last]
    if (!from || !to) return
    const text = textRef.current.slice(from.start, to.end).trim()
    if (!text) return
    suppressClickRef.current = true
    setTimeout(() => {
      suppressClickRef.current = false
    }, 0)
    setSelected(null)
    setPhrase({ text, first, last, sentence: from.sentence || '' })
  }

  useEffect(() => {
    function onUp() {
      finishDrag()
    }
    window.addEventListener('mouseup', onUp)
    return () => window.removeEventListener('mouseup', onUp)
  })

  async function selectWord(token, index) {
    if (suppressClickRef.current) {
      suppressClickRef.current = false
      return
    }
    haltAudio()
    setPhrase(null)
    setSelected({ index, data: { ...token, surface: token.text } })
    setPanelBusy(true)
    try {
      const result = await api.lookup({ word: token.text, lesson_id: lessonId, sentence: token.sentence })
      const merged = { ...token, ...result, word_id: result.id }
      setSelected((current) => (current && current.index === index ? { index, data: merged } : current))
      setTokens((list) =>
        list.map((item) =>
          item.lemma && item.lemma === merged.lemma
            ? {
                ...item,
                lemma: merged.lemma,
                status: merged.status,
                translation: merged.translation,
                grammar: merged.grammar,
                word_id: merged.id,
              }
            : item,
        ),
      )
      if (merged.is_new) notify?.(`Saved “${merged.lemma}”`)
      onChanged?.()
    } catch (err) {
      notify?.(err.message, 'error')
    } finally {
      setPanelBusy(false)
    }
  }

  async function saveWord(patch) {
    if (!selected) return
    const id = selected.data.id || selected.data.word_id
    if (!id) return
    setPanelBusy(true)
    try {
      const updated = await api.patchWord(id, patch)
      setSelected((current) =>
        current
          ? {
              index: current.index,
              data: {
                ...current.data,
                ...updated,
                surface: current.data.surface || updated.surface,
                word_id: updated.id,
              },
            }
          : current,
      )
      setTokens((list) =>
        list.map((item) =>
          item.lemma === updated.lemma
            ? {
                ...item,
                status: updated.status,
                translation: updated.translation,
                grammar: updated.grammar,
                word_id: updated.id,
              }
            : item,
        ),
      )
      onChanged?.()
    } catch (err) {
      notify?.(err.message, 'error')
    } finally {
      setPanelBusy(false)
    }
  }

  async function removeWord() {
    if (!selected) return
    const id = selected.data.id || selected.data.word_id
    if (!id) return
    if (!window.confirm(`Remove “${selected.data.lemma}” and its history?`)) return
    try {
      await api.deleteWord(id)
      const lemma = selected.data.lemma
      setTokens((list) =>
        list.map((item) =>
          item.lemma === lemma
            ? { ...item, status: 0, translation: null, grammar: '', word_id: null }
            : item,
        ),
      )
      setSelected(null)
      onChanged?.()
      notify?.('Word removed')
    } catch (err) {
      notify?.(err.message, 'error')
    }
  }

  if (loading) {
    return (
      <div className="page">
        <div className="state-card">Loading lesson…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page">
        <div className="state-card hint error">{error}</div>
        <button type="button" className="btn ghost" onClick={onBack}>
          Back to library
        </button>
      </div>
    )
  }

  if (!lesson) return null

  const totals = lessonStats || { uniqueWords: 0, knownWords: 0, learningWords: 0, newWords: 0 }
  const pct = totals.uniqueWords ? Math.round((totals.knownWords / totals.uniqueWords) * 100) : 0
  const sourceLabel = mode === 'youtube' ? 'Video' : mode === 'audio' ? 'Audio' : 'Text'

  function phraseIndex(index) {
    if (dragRange && index >= dragRange.first && index <= dragRange.last) return true
    if (phrase && index >= phrase.first && index <= phrase.last) return true
    return false
  }

  function renderToken(token, index) {
    if (token.kind !== 'word') {
      return (
        <span
          key={index}
          className={`tok${phraseIndex(index) ? ' in-phrase' : ''}`}
          onMouseEnter={() => extendDrag(index)}
        >
          {token.text}
        </span>
      )
    }
    const classes = ['tok', 'w', `st-${token.status || 0}`]
    if (index === activeIndex) classes.push('active')
    if (selected?.index === index) classes.push('selected')
    if (phraseIndex(index)) classes.push('in-phrase')
    return (
      <button
        key={index}
        type="button"
        className={classes.join(' ')}
        ref={index === activeIndex ? activeElRef : undefined}
        title={token.translation ? `${token.lemma} — ${token.translation}` : token.lemma}
        onMouseDown={(event) => {
          event.preventDefault()
          beginDrag(index)
        }}
        onMouseEnter={() => extendDrag(index)}
        onClick={() => selectWord(token, index)}
      >
        {token.text}
      </button>
    )
  }

  return (
    <div className="page reader-page">

      <div className="reader-grid">
        <div className="reader-main">
          <header className="page-head reader-top">
            <div className="reader-heading">
              <button type="button" className="btn ghost small" onClick={onBack}>
                ← Library
              </button>
              <div>
                <h1 className="page-title">{lesson.title}</h1>
                <p className="page-sub">
                  <span className="badge">{sourceLabel}</span>
                  {totals.uniqueWords} unique · {totals.newWords} new · {totals.learningWords} learning ·{' '}
                  {totals.knownWords} known
                </p>
              </div>
            </div>
            <div className="reader-progress" title={`${pct}% known`}>
              <span style={{ width: `${pct}%` }} />
            </div>
          </header>

          {mode === 'youtube' ? (
            <div className="media-frame fixed">
              <div className="yt-host" ref={hostRef} />
            </div>
          ) : null}

          {mode === 'audio' ? (
            <div className="media-frame audio-frame fixed">
              <audio
                ref={audioRef}
                src={lesson.audio_url}
                controls
                preload="metadata"
                onPlay={() => {
                  playingRef.current = true
                  setPlaying(true)
                  setMediaError('')
                }}
                onPause={() => {
                  playingRef.current = false
                  setPlaying(false)
                }}
                onEnded={() => {
                  playingRef.current = false
                  setPlaying(false)
                  setActiveIndex(-1)
                }}
                onTimeUpdate={(event) => highlightAtTime(event.currentTarget.currentTime)}
                onError={() => setMediaError('Could not play the audio URL')}
              />
              <p className="hint">Audio only highlights when timed cues are attached to this lesson.</p>
            </div>
          ) : null}

          <div className="audiobar">
            <button type="button" className="btn primary play" onClick={play} disabled={playing}>
              Play
            </button>
            <button type="button" className="btn ghost small" onClick={pause} disabled={!playing}>
              Pause
            </button>
            <button type="button" className="btn ghost small" onClick={restart}>
              Restart
            </button>
            {mode === 'tts' ? (
              <label className="rate">
                Speed
                <select
                  className="select"
                  value={rate}
                  onChange={(event) => changeRate(Number(event.target.value))}
                >
                  {RATES.map((value) => (
                    <option key={value} value={value}>
                      {value}×
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <span className="spacer" />
            <span className="stat-mini">
              {mode === 'youtube'
                ? 'Video follows the text'
                : mode === 'audio'
                  ? 'Audio follows the text'
                  : 'Browser voice'}
            </span>
          </div>

          {mediaError ? <p className="hint error hint-inline">{mediaError}</p> : null}

          <article className={`reader-text scrollable${dragging ? ' dragging' : ''}`}>{tokens.map(renderToken)}</article>

          <div className="legend">
            {STATUSES.map((item) => (
              <span key={item.value} className="legend-item">
                <span className="dot" style={{ background: item.color }} />
                {item.label}
              </span>
            ))}
          </div>

          {mode === 'tts' && !lesson.cues?.length ? (
            <p className="hint hint-block">
              Highlighting follows the browser voice. For exact word timing, import this as a YouTube lesson
              with timed cues.
            </p>
          ) : null}
        </div>

        {phrase ? (
          <PhrasePanel
            phrase={phrase}
            lessonId={lessonId}
            onClose={() => setPhrase(null)}
            onSaved={(data) => {
              notify?.(data?.is_new ? `Saved “${data.lemma}”` : 'Phrase added')
              onChanged?.()
              setPhrase(null)
            }}
          />
        ) : selected ? (
          <WordPanel
            word={selected.data}
            busy={panelBusy}
            onClose={() => setSelected(null)}
            onSave={saveWord}
            onRemove={removeWord}
            onPlayWord={() => playWord(selected.index)}
          />
        ) : (
          <aside className="word-panel empty">
            <p>Tap any word to see its meaning and save it. Drag across words to grab a phrase.</p>
          </aside>
        )}
      </div>
    </div>
  )
}
