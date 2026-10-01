import { ChatMessage } from './chat-store';
import { describeAction, HubNames } from './describe';
import { collectSources } from './sources';

/** The conversation as Markdown, including what the agent did and the data sources. */
export function conversationToMarkdown(messages: ChatMessage[], names: HubNames, exportedAt = new Date()): string {
  const lines = [
    '# Weather Risk Intelligence: conversation export',
    '',
    `_Exported ${exportedAt.toISOString().slice(0, 16).replace('T', ' ')} UTC. Scores are relative operational exposure (0–100), not probabilities of closure or loss._`,
    '',
  ];
  for (const message of messages) {
    if (message.role === 'user') {
      lines.push(`## Question`, '', message.text, '');
    } else if (message.role === 'agent') {
      lines.push('### Answer', '', message.text, '');
      if (message.actions?.length) {
        lines.push('**How this was calculated:**', '');
        for (const action of message.actions) {
          lines.push(`- ${describeAction(action, names)} (${action.status})`);
        }
        lines.push('');
      }
      const sources = collectSources(message.results ?? []);
      if (sources.length) lines.push(`**Data sources:** ${sources.join('; ')}`, '');
      if (message.warnings?.length) {
        lines.push('**Caveats:**', '', ...message.warnings.map((w) => `- ${w}`), '');
      }
    } else {
      lines.push(`> ⚠ ${message.text}`, '');
    }
  }
  return lines.join('\n');
}

export function downloadText(filename: string, content: string, type = 'text/markdown'): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
