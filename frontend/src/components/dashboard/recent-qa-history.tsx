import { Card, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * 最近问答历史 —— **契约外，当前不接数据**。
 *
 * ⚠️ 原实现消费 `GET /api/v1/qa/history`：该端点**不在契约内**，
 * `shouldMock()` 对它恒返回 true（`api/client.ts:68-71`），屏上的
 * 「问题 / 时间 / 引用数」实为 Mock 常量——关掉 Mock 开关也不会变真。
 *
 * 按红线（A16「诚实可核」、plan §7.2 零假数据）改为**明示未接入**；
 * 后端补齐该端点后，这里再换成真实列表。
 *
 * 卡片骨架保留：位置留着，是为了让"缺口"可见，而不是让假数据可见。
 */
export function RecentQaHistory() {
  return (
    <Card className="gap-0">
      <CardHeader className="px-5 pt-4 pb-3">
        <CardTitle>最近问答历史</CardTitle>
      </CardHeader>

      <p className="px-5 py-8 text-center text-[12.5px] text-muted-foreground">
        未接入：契约缺 GET /api/v1/qa/history
      </p>
    </Card>
  );
}
