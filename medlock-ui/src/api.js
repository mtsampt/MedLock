// Real station API only. Replay is explicitly selected by the backend CLI.
const API_URL = import.meta.env?.VITE_API_URL || ''
const SCREENS = new Set(['start', 'supplies', 'prep', 'check', 'checking', 'result', 'done'])

export function validateState(value) {
  const bad = () => { throw new Error('Invalid station response') }
  if (!value || typeof value !== 'object' || typeof value.session_id !== 'string' ||
      !Number.isInteger(value.revision) || !SCREENS.has(value.screen) ||
      !Array.isArray(value.confirmed) || typeof value.simulated !== 'boolean' ||
      typeof value.help_open !== 'boolean' || typeof value.seated !== 'boolean') bad()
  const p = value.protocol
  if (!p || typeof p.medication !== 'string' || !Array.isArray(p.supplies) || !p.supplies.length ||
      !Array.isArray(p.prep_steps) || !p.prep_steps.length ||
      p.supplies.some(item => !item || typeof item.id !== 'string' || typeof item.label !== 'string') ||
      p.prep_steps.some(item => !item || typeof item.title !== 'string' || typeof item.detail !== 'string')) bad()
  if (value.screen === 'supplies' && (!Number.isInteger(value.supply_index) || value.supply_index < 0 || value.supply_index >= p.supplies.length)) bad()
  if (value.screen === 'prep' && (!Number.isInteger(value.prep_index) || value.prep_index < 0 || value.prep_index >= p.prep_steps.length)) bad()
  if (value.screen === 'result' || value.screen === 'done') {
    const r = value.result
    if (!r || !['pass', 'fix', 'unable'].includes(r.verdict) || typeof r.reason !== 'string') bad()
    if (r.volume_ml != null && (typeof r.volume_ml !== 'number' || !Number.isFinite(r.volume_ml) || r.volume_ml < 0)) bad()
    if (r.verdict === 'pass' && (r.valid !== true || r.air_detected !== false || r.syringe_seated !== true ||
        r.volume_ml == null || typeof p.target_volume_ml !== 'number' || !Number.isFinite(p.target_volume_ml) ||
        typeof p.tolerance_ml !== 'number' || !Number.isFinite(p.tolerance_ml) || p.tolerance_ml <= 0 ||
        Math.abs(r.volume_ml - p.target_volume_ml) > p.tolerance_ml || !value.check_id ||
        r.check_id !== value.check_id || r.session_id !== value.session_id)) throw new Error('Incomplete pass response')
  }
  return value
}

export async function request(path, options = {}, fetcher = fetch) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetcher(`${API_URL}/api${path}`, { ...options, signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...options.headers } })
    const data = await response.json()
    if (!response.ok) throw new Error(data.error || `Station request failed (${response.status})`)
    return data
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Station timed out. Reconnect to check its current state.')
    throw error
  } finally { clearTimeout(timeout) }
}

export const getState = async () => validateState(await request('/state'))
export const sendAction = async (action, state) => validateState(await request(action === 'capture' ? '/check' : '/action', {
  method: 'POST', body: JSON.stringify({ action, session_id: state.session_id, revision: state.revision }),
}))
export const getSupplies = () => request('/supplies')
export const logEvent = (event, check_id = null) => request('/log', { method: 'POST', body: JSON.stringify({ event, check_id }) })
