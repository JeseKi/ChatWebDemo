export function resolveErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return '请求失败'
}
