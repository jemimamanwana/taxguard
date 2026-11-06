export type User = { username: string; full_name: string; role: string; tin?: string | null }

const TOKEN_KEY = 'll_token'
const USER_KEY = 'll_user'

function safeGet(k: string): string | null {
  try { return localStorage.getItem(k) } catch { return null }
}
function safeSet(k: string, v: string | null) {
  try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v) } catch { /* private mode */ }
}

let memToken: string | null = safeGet(TOKEN_KEY)

export const session = {
  token: () => memToken,
  user: (): User | null => { const u = safeGet(USER_KEY); return u ? JSON.parse(u) : null },
  set(token: string, user: User) { memToken = token; safeSet(TOKEN_KEY, token); safeSet(USER_KEY, JSON.stringify(user)) },
  clear() { memToken = null; safeSet(TOKEN_KEY, null); safeSet(USER_KEY, null) },
}

export class ApiError extends Error {
  status: number
  constructor(status: number, msg: string) { super(msg); this.status = status }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string> || {}) }
  if (memToken) headers['Authorization'] = `Bearer ${memToken}`
  let body = opts.body
  if (opts.json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.json) }
  const r = await fetch(`/api${path}`, { ...opts, headers, body })
  if (r.status === 401 && !path.startsWith('/auth/login')) { session.clear(); window.location.href = '/login' }
  if (!r.ok) {
    let msg = r.statusText
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* */ }
    throw new ApiError(r.status, msg)
  }
  return r.json()
}

export async function apiBlobUrl(path: string): Promise<string> {
  const r = await fetch(`/api${path}`, { headers: memToken ? { Authorization: `Bearer ${memToken}` } : {} })
  if (!r.ok) throw new ApiError(r.status, r.statusText)
  return URL.createObjectURL(await r.blob())
}

/** Client-side compression for weak connections: max 1600px, JPEG q=0.8 */
export async function compressImage(file: File, maxSide = 1600, quality = 0.8): Promise<{ blob: Blob; before: number; after: number }> {
  const bmp = await createImageBitmap(file)
  const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height))
  const c = document.createElement('canvas')
  c.width = Math.round(bmp.width * scale); c.height = Math.round(bmp.height * scale)
  c.getContext('2d')!.drawImage(bmp, 0, 0, c.width, c.height)
  const blob: Blob = await new Promise(res => c.toBlob(b => res(b!), 'image/jpeg', quality))
  return { blob, before: file.size, after: blob.size }
}
