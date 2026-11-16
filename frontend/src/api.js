/**
 * 后端接口封装。
 * 开发时走 vite 代理（/api → http://127.0.0.1:8000），不用管跨域。
 */
const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!res.ok) {
    let detail = `请求失败（${res.status}）`
    try {
      const j = await res.json()
      if (typeof j.detail === 'string') {
        detail = j.detail
      } else if (Array.isArray(j.detail)) {
        // Pydantic 校验错误是数组，取每条的错误信息
        detail = j.detail.map((d) => `${(d.loc || []).slice(-1)[0] || ''} ${d.msg}`).join('；')
      }
    } catch (e) {
      /* 响应不是 JSON 就用默认文案 */
    }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  health: () => request('/health'),
  options: () => request('/meta/options'),
  generate: (body) => request('/plans/generate', { method: 'POST', body: JSON.stringify(body) }),
  save: (body) => request('/plans', { method: 'POST', body: JSON.stringify(body) }),
  list: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null))
    return request('/plans' + (qs.toString() ? `?${qs}` : ''))
  },
  detail: (id) => request('/plans/' + id),
  remove: (id) => request('/plans/' + id, { method: 'DELETE' }),
  stats: () => request('/plans/stats'),
  task: (id) => request('/plans/task/' + id),
  extract: (body) => request('/chat/extract', { method: 'POST', body: JSON.stringify(body) }),
}
