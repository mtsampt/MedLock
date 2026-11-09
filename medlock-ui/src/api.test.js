import test from 'node:test'
import assert from 'node:assert/strict'
import { request, validateState } from './api.js'

const state = { session_id: 'test', revision: 1, screen: 'start', confirmed: [], simulated: true, help_open: false, seated: false, protocol: { medication: 'Bench', supplies: [{id:'syringe',label:'Syringe'}], prep_steps: [{title:'Prep',detail:'Bench only'}] } }
test('rejects malformed state and incomplete passes', () => {
  assert.equal(validateState(state), state)
  assert.throws(() => validateState({ ...state, screen: 'injection' }))
  assert.throws(() => validateState({ ...state, screen: 'supplies', supply_index: 99 }))
  assert.throws(() => validateState({ ...state, protocol: {supplies:[],prep_steps:[]} }))
  assert.throws(() => validateState({ ...state, screen: 'result', result: { verdict: 'pass', reason: 'fake' } }))
  assert.throws(() => validateState({ ...state, screen: 'result', result: { verdict: 'unknown', reason: 'fake' } }))
})
test('HTTP errors and invalid JSON are surfaced, with no mock fallback', async () => {
  await assert.rejects(request('/check', {}, async () => ({ ok: false, json: async () => ({ error: 'Busy' }) })), /Busy/)
  await assert.rejects(request('/state', {}, async () => ({ ok: true, json: async () => { throw new SyntaxError('bad JSON') } })), /bad JSON/)
  await assert.rejects(request('/state', {}, async () => { throw new TypeError('Offline') }), /Offline/)
})
test('requests target one local API and preserve action payload', async () => {
  const body = JSON.stringify({ action: 'begin', revision: 1, session_id: 'test' })
  const result = await request('/action', { method: 'POST', body }, async (url, options) => {
    assert.equal(url, '/api/action')
    assert.equal(options.body, body)
    assert.equal(options.method, 'POST')
    return { ok: true, json: async () => state }
  })
  assert.equal(result, state)
})
