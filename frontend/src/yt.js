let loader = null

export function loadYouTubeApi() {
  if (typeof window === 'undefined') return Promise.reject(new Error('YouTube API is unavailable'))
  if (window.YT?.Player) return Promise.resolve(window.YT)
  if (loader) return loader

  loader = new Promise((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady
    const script = document.querySelector('script[data-yt-api]')
    const timer = setTimeout(() => {
      loader = null
      reject(new Error('YouTube player timed out while loading'))
    }, 15000)

    window.onYouTubeIframeAPIReady = () => {
      if (typeof previous === 'function') previous()
      clearTimeout(timer)
      if (window.YT?.Player) {
        resolve(window.YT)
      } else {
        loader = null
        reject(new Error('YouTube player failed to initialise'))
      }
    }

    if (script) return

    const element = document.createElement('script')
    element.src = 'https://www.youtube.com/iframe_api'
    element.async = true
    element.dataset.ytApi = 'true'
    element.onerror = () => {
      clearTimeout(timer)
      loader = null
      reject(new Error('Could not load the YouTube player'))
    }
    document.head.appendChild(element)
  })

  return loader
}
