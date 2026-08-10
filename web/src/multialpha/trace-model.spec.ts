import { describe, expect, it } from 'vitest'

import { deriveTraceStatus } from './trace-model'
import type { TraceMessage } from './types'

const message = (tag: string, content: unknown = {}, loopId: number | null = 0): TraceMessage => ({
  tag,
  content,
  loop_id: loopId,
})

describe('deriveTraceStatus', () => {
  it('keeps running after a complete loop with rejected SOTA feedback', () => {
    const messages = [
      message('research.hypothesis'),
      message('feedback.metric', { result: '{"IC":0.01}' }),
      message('feedback.hypothesis_feedback', { decision: false }),
    ]

    expect(deriveTraceStatus(messages)).toBe('running')
  })

  it('keeps running after accepted feedback until the worker exits', () => {
    const messages = [
      message('feedback.metric', { result: '{"IC":0.02}' }),
      message('feedback.hypothesis_feedback', { decision: true }),
    ]

    expect(deriveTraceStatus(messages)).toBe('running')
  })

  it('maps a zero END code to done', () => {
    expect(deriveTraceStatus([message('END', { end_code: 0 }, null)])).toBe('done')
  })

  it.each([-1, -2, 1, 137, undefined])('maps END code %s to error', endCode => {
    expect(deriveTraceStatus([message('END', { end_code: endCode }, null)])).toBe('error')
  })
})
