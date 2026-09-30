# 离线蒸馏曲线切点选择与产率核对系统

用于化工培训：根据给定的**离线累积蒸馏试验曲线**选择馏分切点、核对各段产率、显示缺口/重叠/残余量，并导出插值方法与适用范围。

> 本系统只处理题目给定的离线试验数据，不连接现场仪表，也不向真实装置发送任何控制动作。

## 功能

- React 显示温度—累计回收比例曲线，并在用户调整切点时显示：
  - 各馏分温度、平均密度、体积%与质量%产率；
  - 相邻切点相等导致的零宽度馏分；
  - 馏分段重叠、内部缺口、前段未分配、尾段残余/未分配；
  - 残油、损失或未拆分残余量及总量。
- FastAPI + NumPy + SciPy：
  - 使用 SciPy `PchipInterpolator`（PCHIP，保形分段三次 Hermite 插值，`extrapolate=False`）；
  - 曲线温度下降、回收比例重复/倒退、回收总量异常时先返回核实提示；
  - 密度按源回收比例分段线性变化，用解析积分完成质量%与体积%的有依据换算；
  - 不把质量百分比和体积百分比当成同一个横轴；
  - 缺失 0% 温度时只说明起始温度不可得，不向低温侧外推；最高测点以外不构造高温数据。
- PostgreSQL 保存：
  - 试验条件、样品/装置说明、进料密度、残油和损失；
  - 累积曲线点、随馏分变化的密度点；
  - 切点方案和完整核对结果。

## 内置算例

1. `OFFLINE-GOOD-01`：完整残油/损失、密度随馏分变化、方案中有缺口；可切换质量%与体积%。
2. `OFFLINE-MISS-END-02`：最高仅到 78% 回收；尝试超过 78% 的切点会报“不外推”错误。
3. `OFFLINE-EQUAL-CUT-03`：包含相邻切点相等（零宽度）与重叠区间。

## 一键启动

需要 Docker 与 Docker Compose：

```bash
docker compose up --build
```

- 前端：http://localhost:8080
- API 文档：http://localhost:8000/docs
- PostgreSQL：localhost:5432，库名/用户/密码均为 `distill`

后端启动时自动建表并写入三个离线教学算例及方案。

## 本地开发

后端：

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://distill:distill@localhost:5432/distillation'
uvicorn app.main:app --reload
pytest
```

前端：

```bash
cd frontend
npm install
npm run dev
```

Vite 将 `/api` 代理到 `http://localhost:8000`。

## 密度换算定义

原曲线为体积回收百分比 `x_v` 时，累计质量回收百分比为：

\[
M(x_v)=\int_0^{x_v}\frac{\rho_D(\xi)}{\rho_F}\,d\xi
\]

原曲线为质量回收百分比 `x_m` 时，累计体积回收百分比为：

\[
V(x_m)=\int_0^{x_m}\frac{\rho_F}{\rho_D(\xi)}\,d\xi
\]

其中：

- `ρ_D(x)`：已回收馏出物密度，按源回收比例分段线性变化；
- `ρ_F`：进料密度；
- 切点从一个基准转换到另一个基准时通过上述单调累计关系反查；
- 残油和损失只有在提供相应密度时才折算到另一基准，否则显式标为“未拆分残余量”，不虚构数值。

## 平衡定义

每个基准均按下列定义核对：

```text
已命名馏分合计（重叠区间只计一次）
+ 未分配缺口/前段
+ 尾段内未分配
+ 残油
+ 损失
= 100%
```

若未同时提供残油和损失，则把 100% 与已回收量之间的差额列为“未拆分残余量”。若给出的回收+残油+损失显著不等于 100%，系统先要求核实数据。

## 导出

在界面对方案点击“核对并保存方案”后，可导出：

- JSON：包含试验条件、密度、方案、每段产率、平衡、问题、插值公式和适用范围；
- CSV：适合培训讲评和离线留档。

导出文件明确标注 `offline_only: true`、PCHIP 不启用外推以及温度有效回收范围。
