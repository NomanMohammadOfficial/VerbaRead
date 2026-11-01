export const STATUSES = [
  { value: 0, label: 'Unknown', color: '#64748b' },
  { value: 1, label: 'New', color: '#3b82f6' },
  { value: 2, label: 'Learning', color: '#f59e0b' },
  { value: 3, label: 'Familiar', color: '#84cc16' },
  { value: 4, label: 'Known', color: '#22c55e' },
]

export function statusMeta(value) {
  return STATUSES.find((item) => item.value === Number(value)) || STATUSES[0]
}
