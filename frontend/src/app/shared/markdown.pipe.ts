import { Pipe, PipeTransform } from '@angular/core';
import { marked } from 'marked';

/** Agent answers are Markdown. Rendered HTML is bound with [innerHTML], which Angular sanitizes. */
@Pipe({ name: 'markdown' })
export class MarkdownPipe implements PipeTransform {
  transform(text: string | null | undefined): string {
    return text ? (marked.parse(text, { async: false, gfm: true, breaks: true }) as string) : '';
  }
}
