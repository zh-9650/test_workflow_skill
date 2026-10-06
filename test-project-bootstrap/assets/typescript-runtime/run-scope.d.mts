export declare function resolveApiScriptScope(
  automationDir: string,
  env?: NodeJS.ProcessEnv,
  options?: { prepareAttempt?: boolean; validateOnly?: boolean },
): { runDir: string; target: string; absoluteTarget: string; include: string; resultsDir: string };

export declare function resolveUiScriptScope(
  automationDir: string,
  env?: NodeJS.ProcessEnv,
  options?: { prepareAttempt?: boolean; validateOnly?: boolean },
): { runDir: string; target: string; absoluteTarget: string; testDir: string; testMatch: string; resultsDir: string };
