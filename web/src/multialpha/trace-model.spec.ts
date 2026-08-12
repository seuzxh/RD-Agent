import { describe, expect, it } from 'vitest'

import { derivePipelineStages, deriveTraceStatus } from './trace-model'
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

describe('derivePipelineStages', () => {
  it.each(['done', 'error'] as const)('does not show a loading stage for a %s task with missing outputs', status => {
    const stages = derivePipelineStages([], status)
    expect(stages.every(stage => stage.state === 'idle')).toBe(true)
  })

  it('shows the first missing stage only while the task is running', () => {
    const stages = derivePipelineStages([message('research.hypothesis')], 'running')
    expect(stages.map(stage => stage.state)).toEqual(['done', 'active', 'idle', 'idle', 'idle'])
  })

  it('keeps completed stages done but leaves missing stages idle after an error', () => {
    const stages = derivePipelineStages([message('research.hypothesis'), message('research.tasks')], 'error')
    expect(stages.map(stage => stage.state)).toEqual(['done', 'done', 'idle', 'idle', 'idle'])
  })
})
