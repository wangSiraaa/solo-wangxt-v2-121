import React, { useEffect, useMemo, useState } from 'react'
import { api } from './api'

const basisLabel = (b) => b === 'mass' ? '质量百分比' : '体积百分比'
const number = (v, digits = 2) => v === null || v === undefined ? '—' : Number(v).toFixed(digits)

function Badge({ issue }) {
  return <span className={`badge ${issue.severity}`}>{issue.severity === 'error' ? '错误' : issue.severity === 'warning' ? '提示' : '说明'}：{issue.message}</span>
}

function CurveChart({ trial, result, basis, fractions }) {
  const width = 920
  const height = 390
  const margin = { left: 70, right: 30, top: 25, bottom: 58 }
  const needsConvertedCurve = Boolean(trial && (result?.basis || basis) !== trial.curve_basis && !result)
  const points = result?.display_points?.length
    ? result.display_points
    : (!needsConvertedCurve
      ? (trial?.curve_points || [])
        .filter(p => p.temperature_c !== null && p.temperature_c !== undefined)
        .map(p => ({ selected_recovery_percent: p.recovery, temperature_c: p.temperature_c }))
      : [])
  const temps = trial?.curve_points?.map(p => p.temperature_c).filter(v => v !== null && v !== undefined) || []
  const sourceMax = trial ? Math.max(...trial.curve_points.map(p => p.recovery)) : 100
  const sourceMin = trial ? Math.min(...trial.curve_points.filter(p => p.temperature_c !== null && p.temperature_c !== undefined).map(p => p.recovery)) : 0
  const maxX = result?.selected_interpolation_range?.[1] ?? sourceMax
  const minX = result?.selected_interpolation_range?.[0] ?? sourceMin
  const maxT = Math.max(100, ...(temps.length ? temps : [600]))
  const minT = Math.min(0, ...(temps.length ? temps : [0]))
  const xScale = (x) => margin.left + (x / 100) * (width - margin.left - margin.right)
  const yScale = (t) => height - margin.bottom - ((t - minT) / (maxT - minT)) * (height - margin.top - margin.bottom)
  const path = points.map((p, i) => `${i ? 'L' : 'M'} ${xScale(p.selected_recovery_percent)} ${yScale(p.temperature_c)}`).join(' ')

  const ticks = Array.from({ length: 11 }, (_, i) => i * 10)
  const tempTicks = Array.from({ length: 7 }, (_, i) => Math.round(minT + i * (maxT - minT) / 6))

  const colored = fractions.filter(f => Number.isFinite(Number(f.start)) && Number(f.end) >= Number(f.start))
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="chart" role="img" aria-label="温度对回收比例累积蒸馏曲线">
      {tempTicks.map(t => (
        <g key={`t${t}`}>
          <line x1={margin.left} x2={width - margin.right} y1={yScale(t)} y2={yScale(t)} className="grid" />
          <text x={margin.left - 8} y={yScale(t) + 4} textAnchor="end">{t}</text>
        </g>
      ))}
      {ticks.map(x => (
        <g key={`x${x}`}>
          <line x1={xScale(x)} x2={xScale(x)} y1={margin.top} y2={height - margin.bottom} className="grid faint" />
          <text x={xScale(x)} y={height - margin.bottom + 22} textAnchor="middle">{x}%</text>
        </g>
      ))}
      {minX > 0 && <rect x={xScale(0)} y={margin.top} width={xScale(minX) - xScale(0)} height={height - margin.top - margin.bottom} className="no-data-zone" />}
      {maxX < 100 && <rect x={xScale(maxX)} y={margin.top} width={xScale(100) - xScale(maxX)} height={height - margin.top - margin.bottom} className="no-data-zone" />}
      {colored.map((f, i) => {
        const a = Number(f.start), b = Number(f.end)
        if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a || b > maxX) return null
        return <rect key={f.name + i} x={xScale(a)} y={margin.top} width={xScale(b) - xScale(a)} height={height - margin.top - margin.bottom}
          fill={`hsl(${(i * 47) % 360} 70% 55%)`} opacity="0.13" />
      })}
      {path && <path d={path} className="curve-path" />}
      {points.map((p, i) => <circle key={i} cx={xScale(p.selected_recovery_percent)} cy={yScale(p.temperature_c)} r="3.2" className="curve-dot" />)}
      {colored.map((f, i) => [Number(f.start), Number(f.end)].map((x, j) => Number.isFinite(x) && x <= maxX ? (
        <g key={`${f.name}-${j}`}>
          <line x1={xScale(x)} x2={xScale(x)} y1={margin.top} y2={height - margin.bottom} className="cut-line" />
          <text x={xScale(x)} y={margin.top + 14 + (i % 4) * 13} textAnchor="middle" className="cut-label">{number(x, 1)}</text>
        </g>
      ) : null))}
      {minX > 0 && <text x={(xScale(0) + xScale(minX)) / 2} y={margin.top + 28} textAnchor="middle" className="no-data-text">缺0%端点</text>}
      {maxX < 100 && <text x={(xScale(maxX) + xScale(100)) / 2} y={margin.top + 28} textAnchor="middle" className="no-data-text">无高温数据，不外推</text>}
      {needsConvertedCurve && <text x={width / 2} y={height / 2} textAnchor="middle" className="no-data-text">已切换到{basisLabel(basis)}；点击“核对切点方案”后按密度生成转换曲线</text>}
      <line x1={margin.left} x2={width - margin.right} y1={height - margin.bottom} y2={height - margin.bottom} className="axis" />
      <line x1={margin.left} x2={margin.left} y1={margin.top} y2={height - margin.bottom} className="axis" />
      <text x={width / 2} y={height - 12} textAnchor="middle" className="axis-title">累计回收比例（{basisLabel(result?.basis || trial?.curve_basis)}）</text>
      <text transform={`translate(18 ${height / 2}) rotate(-90)`} textAnchor="middle" className="axis-title">温度 °C</text>
    </svg>
  )
}

export default function App() {
  const [trials, setTrials] = useState([])
  const [trialId, setTrialId] = useState('')
  const [basis, setBasis] = useState('volume')
  const [fractions, setFractions] = useState([])
  const [result, setResult] = useState(null)
  const [plans, setPlans] = useState([])
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { api.listTrials().then(rows => { setTrials(rows); if (rows[0]) setTrialId(rows[0].id) }).catch(e => setError(e.message)) }, [])
  const trial = useMemo(() => trials.find(t => t.id === Number(trialId)), [trials, trialId])

  useEffect(() => {
    if (!trialId) return
    setResult(null)
    api.listPlans(trialId).then(rows => {
      setPlans(rows)
      if (rows[0]) {
        const plan = rows[0]
        setBasis(plan.basis)
        setFractions(plan.result.fractions.map(f => ({ name: f.name, start: f.start ?? '', end: f.end ?? '' })))
        setResult({ ...plan.result, saved_plan_id: plan.id })
      }
    }).catch(() => setPlans([]))
  }, [trialId])

  useEffect(() => {
    if (trial && !plans.some(p => p.trial_id === trial.id)) setBasis(trial.curve_basis)
  }, [trial, plans])

  async function evaluate(save = false) {
    setBusy(true); setSaving(save); setError('')
    try {
      const payload = {
        basis,
        save,
        plan_name: save ? `UI方案 ${new Date().toLocaleString('zh-CN')}` : null,
        fractions: fractions.map(f => ({
          name: f.name || '未命名',
          start: f.start === '' ? null : Number(f.start),
          end: f.end === '' ? null : Number(f.end)
        }))
      }
      const res = await api.evaluate(trialId, payload)
      setResult(res)
      if (save) setPlans(await api.listPlans(trialId))
    } catch (e) { setError(e.message) } finally { setBusy(false); setSaving(false) }
  }

  function updateFraction(index, key, value) {
    setFractions(rows => rows.map((f, i) => i === index ? { ...f, [key]: value } : f))
    setResult(prev => prev?.saved_plan_id ? { ...prev, saved_plan_id: null } : prev)
  }

  async function loadPlan(planId) {
    const plan = plans.find(p => p.id === planId)
    if (!plan) return
    setBasis(plan.basis)
    setFractions(plan.result.fractions.map(f => ({ name: f.name, start: f.start ?? '', end: f.end ?? '' })))
    setResult({ ...plan.result, saved_plan_id: plan.id })
  }

  const balance = result?.target_balance
  const sourceBalance = result?.source_balance
  const sourceMaxAllowed = trial ? Math.max(...trial.curve_points.map(p => p.recovery)) : 100
  const maxAllowed = result?.selected_interpolation_range?.[1] ?? sourceMaxAllowed

  return (
    <main>
      <header>
        <div>
          <h1>离线蒸馏曲线切点选择与产率核对</h1>
          <p className="subtle">仅使用题目给定的离线试验数据；本应用不连接、不控制真实装置。</p>
        </div>
      </header>

      <section className="card toolbar">
        <label>离线试验
          <select value={trialId} onChange={e => setTrialId(e.target.value)}>
            {trials.map(t => <option key={t.id} value={t.id}>{t.code} — {t.name}</option>)}
          </select>
        </label>
        <label>显示/选择基准
          <select value={basis} onChange={e => { setBasis(e.target.value); setResult(null) }}>
            <option value="volume">体积百分比</option>
            <option value="mass">质量百分比</option>
          </select>
        </label>
        {plans.length > 0 && <label>已保存教学方案
          <select value="" onChange={e => loadPlan(Number(e.target.value))}>
            <option value="">选择方案载入…</option>
            {plans.map(p => <option key={p.id} value={p.id}>{p.name}{p.valid ? '' : '（需核实）'}</option>)}
          </select>
        </label>}
        <button onClick={() => evaluate(false)} disabled={!trial || busy}>{busy && !saving ? '计算中…' : '核对切点方案'}</button>
        <button className="secondary" onClick={() => evaluate(true)} disabled={!trial || busy}>{saving ? '保存中…' : '核对并保存方案'}</button>
      </section>

      {trial && (
        <section className="grid two">
          <div className="card">
            <h2>试验条件与数据</h2>
            <dl className="meta">
              <dt>样品</dt><dd>{trial.sample_type}</dd>
              <dt>原始曲线横轴</dt><dd>{basisLabel(trial.curve_basis)}</dd>
              <dt>进料密度</dt><dd>{number(trial.feed_density, 3)} g/cm³</dd>
              <dt>残油 / 损失</dt><dd>{number(trial.measured_residue)}% / {number(trial.measured_loss)}%</dd>
              <dt>装置说明</dt><dd>{trial.apparatus}</dd>
              <dt>数据边界</dt><dd>最高回收 {maxAllowed}%；温度插值不得越过该高温点。</dd>
            </dl>
            <div className="table-wrap">
              <table><thead><tr><th>{basisLabel(trial.curve_basis)}</th><th>温度°C</th><th>密度 g/cm³</th></tr></thead>
                <tbody>{Array.from(new Set([
                  ...trial.curve_points.map(p => p.recovery),
                  ...trial.density_points.map(p => p.recovery)
                ])).sort((a, b) => a - b).map((x) => {
                  const curvePoint = trial.curve_points.find(p => p.recovery === x)
                  const densityPoint = trial.density_points.find(p => p.recovery === x)
                  return <tr key={x}><td>{x}</td><td>{curvePoint?.temperature_c ?? '—'}</td><td>{densityPoint?.density_g_cm3 ?? '—'}</td></tr>
                })}</tbody>
              </table>
            </div>
          </div>
          <div className="card">
            <h2>累积蒸馏曲线</h2>
            <CurveChart trial={trial} result={result} basis={basis} fractions={fractions} />
            <p className="subtle">阴影为用户定义的馏分区间；红色竖线为切点。空白即缺口，右侧灰区表示没有高温试验点。</p>
          </div>
        </section>
      )}

      <section className="card">
        <div className="section-head"><h2>调整馏分切点（{basisLabel(basis)}）</h2><button onClick={() => { setFractions([...fractions, { name: `馏分${fractions.length + 1}`, start: '', end: '' }]); setResult(prev => prev?.saved_plan_id ? { ...prev, saved_plan_id: null } : prev) }}>添加馏分</button></div>
        <div className="fractions">
          {fractions.map((f, i) => (
            <div className="fraction-row" key={i}>
              <input value={f.name} onChange={e => updateFraction(i, 'name', e.target.value)} aria-label="馏分名称" />
              <label>起点 %<input type="number" min="0" max={maxAllowed} step="0.1" value={f.start} onChange={e => updateFraction(i, 'start', e.target.value)} /></label>
              <input type="range" min="0" max={maxAllowed} step="0.1" value={f.start === '' ? 0 : f.start} onChange={e => updateFraction(i, 'start', e.target.value)} />
              <label>终点 %<input type="number" min="0" max={maxAllowed} step="0.1" value={f.end} onChange={e => updateFraction(i, 'end', e.target.value)} /></label>
              <input type="range" min="0" max={maxAllowed} step="0.1" value={f.end === '' ? 0 : f.end} onChange={e => updateFraction(i, 'end', e.target.value)} />
              <button className="ghost" onClick={() => { setFractions(fractions.filter((_, j) => j !== i)); setResult(prev => prev?.saved_plan_id ? { ...prev, saved_plan_id: null } : prev) }}>删除</button>
            </div>
          ))}
        </div>
      </section>

      {error && <div className="card error-text">{error}</div>}

      {result && <>
        <section className="card">
          <h2>核实结果</h2>
          <div className="issues">{result.issues.length ? result.issues.map((x, i) => <Badge key={i} issue={x} />) : <span className="ok">未发现异常。</span>}</div>
        </section>

        <section className="grid two">
          <div className="card">
            <h2>各馏分产率</h2>
            <div className="table-wrap"><table>
              <thead><tr><th>名称</th><th>起点</th><th>终点</th><th>起温°C</th><th>终温°C</th><th>平均密度</th><th>{basisLabel(result.basis)}产率</th><th>原始基准产率</th><th>状态</th></tr></thead>
              <tbody>{result.fractions.map((f, i) => <tr key={i} className={f.status === 'ok' ? '' : f.status}><td>{f.name}</td><td>{number(f.start, 2)}</td><td>{number(f.end, 2)}</td><td>{number(f.start_temperature_c, 1)}</td><td>{number(f.end_temperature_c, 1)}</td><td>{number(f.average_density_g_cm3, 3)}</td><td>{number(f.target_yield_percent, 2)}</td><td>{number(f.source_yield_percent, 2)}</td><td>{f.status}</td></tr>)}</tbody>
            </table></div>
          </div>
          <div className="card">
            <h2>重叠、缺口与物料平衡</h2>
            <ul className="findings">
              <li>重叠：{result.overlaps.length ? result.overlaps.map(x => `${number(x[0])}–${number(x[1])}%`).join('，') : '无'}</li>
              <li>内部缺口：{result.gaps.length ? result.gaps.map(x => `${number(x[0])}–${number(x[1])}%`).join('，') : '无'}</li>
              <li>前段未分配：{result.leading_gap ? `${number(result.leading_gap[0])}–${number(result.leading_gap[1])}%` : '无'}</li>
              <li>尾段未分配/残余：{result.tail_gap ? `${number(result.tail_gap[0])}–${number(result.tail_gap[1])}%（已回收范围内）` : '无'}</li>
            </ul>
            <BalanceTable title={`选择基准（${basisLabel(result.basis)}）`} b={balance} />
            <BalanceTable title={`原始曲线基准（${basisLabel(result.curve_basis)}）`} b={sourceBalance} />
          </div>
        </section>

        <section className="card">
          <h2>插值、密度换算与适用范围</h2>
          <ul className="method">
            <li>{result.method.temperature_interpolation}</li>
            <li>{result.density_conversion}</li>
            <li>{result.method.density_model}</li>
            <li>温度有效范围：{result.valid_interpolation_range[0]}% – {result.valid_interpolation_range[1]}%（源回收比例），无高温数据时不外推。</li>
            <li>{result.method.balance_rule}</li>
          </ul>
          <div className="actions">
            {result.saved_plan_id ? <>
              <a href={api.exportUrl(result.saved_plan_id, 'json')} target="_blank" rel="noreferrer">导出 JSON</a>
              <a href={api.exportUrl(result.saved_plan_id, 'csv')} target="_blank" rel="noreferrer">导出 CSV</a>
            </> : <span className="subtle">点击“核对并保存方案”后，可导出包含插值方法和适用范围的 JSON/CSV。</span>}
          </div>
        </section>
      </>}
    </main>
  )
}

function BalanceTable({ title, b }) {
  if (!b) return null
  const rows = [
    ['馏分合计（重叠去重）', b.fractions], ['缺口/未分配', b.gaps], ['残油', b.residue],
    ['损失', b.loss], ['未拆分残余量', b.unresolved], ['总量', b.total]
  ]
  return <div className="balance">
    <h3>{title}</h3>
    <table><tbody>{rows.map(([k, v]) => <tr key={k}><td>{k}</td><td className={k === '总量' && Math.abs((v || 0) - 100) > 0.05 ? 'bad' : ''}>{number(v, 3)}%</td></tr>)}</tbody></table>
    <p className="subtle">{b.definition}</p>
  </div>
}
