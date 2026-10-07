import { eventRegistry } from "../config/eventRegistry";
import { derivePhase } from "../state/derivePhase";
import { type StateEnvelope, type WorldOneState } from "../state/schema";
import type { WorldId } from "../config/worldRegistry";

export type RuntimeEventEnvelope = { worldId: WorldId; events: string[] };
const CHOICE_BLOCK_PATTERNS = [
  // 与 charx 一致容忍流式截断：闭合标签缺失时匹配到消息末尾，损坏 JSON 由解析失败兜底
  /<moonlight_choices>\s*([\s\S]*?)\s*(?:<\/moonlight_choices>|$)/gi,
  /<charx_choices>\s*([\s\S]*?)\s*(?:<\/char(?:x(?:_choices)?)?>?|$)/gi,
];

// 平台重新生成可能把被替换的旧回复与新回复同时留在历史里（两条 assistant 相邻）。
// 本应用正常流程中 assistant 消息必然由 user/system 消息间隔，相邻 assistant 只可能是重生成的旧版本，只保留最后一条。
export function dropSupersededAssistantMessages<T extends { role: string }>(messages: readonly T[]): T[] {
  return messages.filter((message, index) => message.role !== "assistant" || messages[index + 1]?.role !== "assistant");
}

export function extractStateEnvelope(content: string, worldId: WorldId = "w1"): RuntimeEventEnvelope | null {
  // 先全局收集所有非空 <e>...</e> 回执：同一条消息可能携带多个事件，
  // 且 <e/> 空回执不得短路掉并存的真实事件
  const compactMatches = Array.from(content.matchAll(/<e>\s*([a-z0-9_.|-]+)\s*<\/e>/gi));
  if (compactMatches.length > 0) {
    const events = compactMatches
      .flatMap((match) => match[1].split("|"))
      .filter(Boolean)
      .map((eventId) => /^w[1-5]\./.test(eventId) ? eventId : `${worldId}.${eventId}`);
    return events.length <= 8 ? { worldId, events } : null;
  }
  // 只有完全没有非空回执时，才接受 <e/> 空回执
  if (/<e\s*\/\s*>/i.test(content)) return { worldId, events: [] };

  const match = content.match(/<moonlight_state>\s*([\s\S]*?)\s*<\/moonlight_state>/i);
  if (!match) return null;

  try {
    const parsed = JSON.parse(match[1]) as { worldId?: unknown; events?: unknown };
    if (parsed.worldId !== worldId || !Array.isArray(parsed.events) || parsed.events.length > 8 || parsed.events.some((item) => typeof item !== "string")) return null;
    return { worldId, events: parsed.events as string[] };
  } catch {
    return null;
  }
}

export function extractRuntimeChoices(content: string): string[] {
  const matches = CHOICE_BLOCK_PATTERNS.flatMap((pattern) => {
    pattern.lastIndex = 0;
    return Array.from(content.matchAll(pattern));
  }).sort((left, right) => (right.index ?? 0) - (left.index ?? 0));
  const match = matches[0];
  if (!match) return [];
  try {
    const parsed = JSON.parse(match[1]);
    if (!Array.isArray(parsed) || parsed.length !== 3) return [];
    const choices = parsed.map((item) => typeof item === "string"
      ? item.trim()
      : item && typeof item === "object" && typeof (item as { text?: unknown }).text === "string"
        ? (item as { text: string }).text.trim()
        : "");
    if (choices.some((item) => item.length < 2 || item.length > 80) || new Set(choices).size !== 3) return [];
    return choices;
  } catch {
    return [];
  }
}

export function runtimeChoicesChanged(previous: readonly string[], next: readonly string[]): boolean {
  if (previous.length !== 3 || next.length !== 3) return true;
  const previousSet = new Set(previous.map((choice) => choice.trim()));
  return next.every((choice) => !previousSet.has(choice.trim()));
}

export function extractLatestRuntimeChoices(messages: readonly { role: string; content: string }[]): string[] {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "assistant") return extractRuntimeChoices(message.content);
  }
  return [];
}

export function stripRuntimeBlocks(content: string): string {
  return content
    // 思维链只供模型推演：与 moonlight 系一致容忍未闭合标签，流式输出时剥到消息末尾，正文出现前不显示半截推演
    .replace(/<thinking>[\s\S]*?(?:<\/thinking>|$)/gi, "")
    // 实验版不把协议说明显示给玩家；兼容旧回复中位于变量块前的分析段。
    .replace(/(?:^|\n)\s*(?:---\s*)?Analysis\s*\n[\s\S]*?(?=\s*<(?:charx_vars|charx_choices)>)/i, "\n")
    .replace(/\\*(?=<UpdateVariable>)[\s\S]*?\\*(?:<\/UpdateVariable>|$)/gi, "")
    .replace(/(?:```\s*)?json\s*:\s*UpdateVariable\s*[\s\S]*?(?:```|$)/gi, "")
    .replace(/<e>\s*[a-z0-9_.|-]+\s*<\/e>/gi, "")
    .replace(/<e\s*\/\s*>/gi, "")
    // moonlight 系三个块与 charx 一致容忍未闭合标签：流式截断时剥到消息末尾，避免裸标签泄漏进正文
    .replace(/<moonlight_state>[\s\S]*?(?:<\/moonlight_state>|$)/gi, "")
    .replace(/<moonlight_status>[\s\S]*?(?:<\/moonlight_status>|$)/gi, "")
    .replace(/<moonlight_choices>[\s\S]*?(?:<\/moonlight_choices>|$)/gi, "")
    .replace(/<charx_choices>[\s\S]*?(?:<\/char(?:x(?:_choices)?)?>?|$)/gi, "")
    .trim();
}

export type ProcessEventsResult = {
  state: WorldOneState;
  applied: string[];
  rejected: string[];
};

export function processEvents(current: WorldOneState, envelope: StateEnvelope): ProcessEventsResult {
  const next = structuredClone(current);
  const applied: string[] = [];
  const rejected: string[] = [];

  for (const eventId of envelope.events) {
    const definition = eventRegistry[eventId];
    if (!definition || next.appliedEventIds.includes(eventId) || definition.requires?.(next) === false) {
      rejected.push(eventId);
      continue;
    }

    definition.apply(next);
    next.appliedEventIds.push(eventId);
    next.systemLog = [`事件确认：${definition.label}`, ...next.systemLog].slice(0, 24);
    applied.push(eventId);
  }

  next.phase = derivePhase(next);
  return { state: next, applied, rejected };
}
