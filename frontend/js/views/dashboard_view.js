export const dashboardViewTemplate = `
<section class="panel">
  <h2>闸口总览</h2>
  <p class="hint">过磅票入闸后裁定超重才放行，驳回进旁路挂起；停用车道当日锁死，正式票与对账流量均零增。</p>
  <div class="hero-cards">
    <div class="hero-card"><span class="t">地磅桥</span><div class="n">{{ dash.bridges ?? '—' }}</div></div>
    <div class="hero-card"><span class="t">开放超重</span><div class="n">{{ dash.open_overloads ?? '—' }}</div></div>
    <div class="hero-card"><span class="t">旁路挂起</span><div class="n">{{ dash.side_pending ?? '—' }}</div></div>
    <div class="hero-card"><span class="t">过磅票</span><div class="n">{{ dash.tickets ?? '—' }}</div></div>
    <div class="hero-card"><span class="t">已放行</span><div class="n">{{ dash.gate_releases ?? '—' }}</div></div>
    <div class="hero-card"><span class="t">已封闸</span><div class="n">{{ dash.gate_seals ?? '—' }}</div></div>
    <div class="hero-card"><span class="t">停用车道</span><div class="n">{{ dash.closed_lanes ?? '—' }}</div></div>
    <div class="hero-card"><span class="t">今日停用锁死</span><div class="n">{{ dash.disabled_locks_today ?? '—' }}</div></div>
  </div>
  <p class="hint" style="margin-top:16px">停用命运册：停用车道被拒过磅即当日锁死，正式票增量 0、对账流量增量 0。</p>
  <table v-if="disabledLedger.length" class="data-table">
    <thead><tr><th>日期</th><th>车道</th><th>状态</th><th>操作人</th><th>正式票增量</th><th>对账流量增量</th><th>裁定</th></tr></thead>
    <tbody>
      <tr v-for="row in disabledLedger" :key="row.id">
        <td>{{ row.ledger_day }}</td>
        <td>{{ row.lane_code }}</td>
        <td>{{ row.lane_status }}</td>
        <td>{{ row.actor }}</td>
        <td>{{ row.formal_ticket_delta }}</td>
        <td>{{ row.reconcile_traffic_delta }}</td>
        <td><span class="badge fail">{{ row.verdict }}</span></td>
      </tr>
    </tbody>
  </table>
  <p class="hint" style="margin-top:16px">骨架：{{ dash.meta && dash.meta.skeleton }}</p>
</section>
`;
