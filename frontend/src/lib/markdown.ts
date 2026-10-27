// A small, safe Markdown renderer for assistant replies. Everything is HTML-escaped first, so
// the model can't inject markup; only the few constructs below are turned into elements.
// Supported: paragraphs, line breaks, ### headings, - and 1. lists, | tables |, `code`,
// **bold**, *italic*, and [links](/path) to app pages or https URLs.

function escape(text: string): string {
	return text
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;')
		.replaceAll("'", '&#39;');
}

function safeHref(url: string): string | null {
	if (url.startsWith('/') && !url.startsWith('//')) return url;
	if (/^https:\/\/[^\s]+$/.test(url)) return url;
	return null;
}

function inline(text: string): string {
	const codes: string[] = [];
	let out = escape(text).replace(/`([^`]+)`/g, (_, c) => {
		codes.push(`<code class="rounded bg-surface-2 px-1">${c}</code>`);
		return `\u0000${codes.length - 1}\u0000`;
	});
	out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (whole, label, url) => {
		const href = safeHref(url.replaceAll('&amp;', '&'));
		if (!href) return label;
		const external = href.startsWith('https:') ? ' target="_blank" rel="noopener"' : '';
		return `<a class="text-accent underline" href="${escape(href)}"${external}>${label}</a>`;
	});
	out = out
		.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
		.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
	return out.replace(/\u0000(\d+)\u0000/g, (_, i) => codes[Number(i)]);
}

function isTableRow(line: string) {
	return /^\s*\|.*\|\s*$/.test(line);
}

function cells(line: string): string[] {
	return line
		.trim()
		.replace(/^\||\|$/g, '')
		.split('|')
		.map((c) => c.trim());
}

export function renderMarkdown(source: string): string {
	const lines = source.replace(/\r/g, '').split('\n');
	const html: string[] = [];
	let i = 0;
	while (i < lines.length) {
		const line = lines[i];
		if (!line.trim()) {
			i++;
			continue;
		}
		const heading = line.match(/^#{1,6}\s+(.*)$/);
		if (heading) {
			html.push(`<p class="font-semibold">${inline(heading[1])}</p>`);
			i++;
			continue;
		}
		if (isTableRow(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
			const head = cells(line);
			i += 2;
			const rows: string[][] = [];
			while (i < lines.length && isTableRow(lines[i])) rows.push(cells(lines[i++]));
			html.push(
				'<div class="overflow-x-auto"><table class="w-full text-sm"><thead><tr>' +
					head
						.map((h) => `<th class="border-b border-border px-2 py-1 text-left">${inline(h)}</th>`)
						.join('') +
					'</tr></thead><tbody>' +
					rows
						.map(
							(r) =>
								'<tr>' +
								r
									.map((c) => `<td class="border-b border-border px-2 py-1">${inline(c)}</td>`)
									.join('') +
								'</tr>'
						)
						.join('') +
					'</tbody></table></div>'
			);
			continue;
		}
		const bullet = /^\s*[-*•]\s+/;
		const numbered = /^\s*\d+[.)]\s+/;
		if (bullet.test(line) || numbered.test(line)) {
			const ordered = numbered.test(line);
			const pattern = ordered ? numbered : bullet;
			const items: string[] = [];
			while (i < lines.length && pattern.test(lines[i])) {
				items.push(`<li>${inline(lines[i].replace(pattern, ''))}</li>`);
				i++;
			}
			const tag = ordered ? 'ol' : 'ul';
			const style = ordered ? 'list-decimal' : 'list-disc';
			html.push(`<${tag} class="${style} space-y-1 pl-5">${items.join('')}</${tag}>`);
			continue;
		}
		const para: string[] = [];
		while (
			i < lines.length &&
			lines[i].trim() &&
			!bullet.test(lines[i]) &&
			!numbered.test(lines[i]) &&
			!/^#{1,6}\s/.test(lines[i]) &&
			!isTableRow(lines[i])
		) {
			para.push(inline(lines[i]));
			i++;
		}
		html.push(`<p>${para.join('<br>')}</p>`);
	}
	return html.join('');
}
