import { Info } from "lucide-react";

import { PlaceholderPage } from "@/components/common/placeholder-page";
import { Badge } from "@/components/ui/badge";

/**
 * 系统设置页（功能预留 + 演示环境标注）。
 *
 * **A16（Sprint 8 批次 D）**：处置方式选「加『演示环境』标注」而**不选**隐藏路由——
 * 隐藏路由会让 plan §7.2「演示剧本 6 步零假数据」硬门槛**失去可核性**（验收者分不清
 * 是"没有这个页面"还是"页面有假数据"）。标注既诚实又可核：本页把"为什么没有配置项"
 * 直接写在页面上，且每条都可回到契约 / 语料目录复核。
 *
 * 事实口径（改动前逐条核对，不写推测内容）：
 * - `contracts/openapi.yaml` **无** `/settings*` 路径 ⇒ 本页既无配置项、也无 Mock 数据；
 * - 演示语料：`docs/annualreport/` 招商局系 2025 年报（10 份 PDF）；
 * - 身份走开发态请求头（`LocalAuthProvider`），非生产认证。
 */
export default function SettingsPage() {
  return (
    <PlaceholderPage
      title="系统设置"
      description="知识库与检索参数的全局配置（当前版本未提供配置能力）。"
      badge={
        <Badge variant="muted" className="gap-1.5">
          <Info className="size-3" />
          演示环境
        </Badge>
      }
      notice={<DemoEnvironmentNotice />}
    />
  );
}

/** 演示环境说明卡：把"演示环境"四个字落成可核的事实清单 */
function DemoEnvironmentNotice() {
  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-white/[0.02] px-4 py-3.5">
      <p className="text-[13px] font-medium text-foreground">
        演示环境（Demo Environment）
      </p>

      <ul className="flex flex-col gap-1.5 text-xs leading-relaxed text-muted-foreground">
        <li>
          <span className="text-foreground">本页无配置项、也无 Mock 数据</span>
          ：契约 <code className="font-mono text-[11px]">openapi.yaml</code>{" "}
          未提供任何 <code className="font-mono text-[11px]">/settings*</code>{" "}
          路径，按「功能预留原则」只保留导航入口，不伪造配置项。
        </li>
        <li>
          <span className="text-foreground">演示语料</span>：
          <code className="font-mono text-[11px]">docs/annualreport/</code>{" "}
          招商局系 2025 年度报告（10 份 PDF）。
        </li>
        <li>
          <span className="text-foreground">真实数据的页面</span>
          ：文档管理 / 知识图谱 / 知识问答 / 疑点清单 / 权限审计均走真实接口（
          <code className="font-mono text-[11px]">
            NEXT_PUBLIC_USE_MOCK=false
          </code>
          ）；知识问答的
          <span className="text-foreground">多轮会话列表</span>
          仍为 Mock，属已知豁免。
        </li>
        <li>
          <span className="text-foreground">非生产认证</span>
          ：身份与租户走开发态请求头{" "}
          <code className="font-mono text-[11px]">X-Org-Id</code> /{" "}
          <code className="font-mono text-[11px]">X-Actor-Id</code>（
          <code className="font-mono text-[11px]">LocalAuthProvider</code>
          ）；限流 60 次 / 分钟 / 接口，超限返回 429{" "}
          <code className="font-mono text-[11px]">RATE_LIMITED</code>。
        </li>
      </ul>
    </div>
  );
}
