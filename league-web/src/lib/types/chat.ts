export type ChatRole = "user" | "assistant";

export type ChatMessage = {
  role: ChatRole;
  content: string;
};

export type ChatTokenData = {text: string};
export type ChatToolCallData = {name: string; label: string};
export type ChatToolResultData = {name: string; ok: boolean};
export type ChatDoneData = {finish_reason: string; rounds: number};
export type ChatErrorData = {detail: string};
