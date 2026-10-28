import { expect, test } from '@playwright/test';
import { renderMarkdown } from '../../src/lib/markdown.ts';

// Regression: a table row with no separator line under it (as when a reply is still streaming
// in) used to loop forever and freeze the tab.
test('a table row without a separator renders as text', () => {
	expect(renderMarkdown('Here you go:\n| Venue | Capacity |')).toBe(
		'<p>Here you go:</p><p>| Venue | Capacity |</p>'
	);
	expect(renderMarkdown('| Venue | Capacity |\n|---|---|\n| CC5 | 40 |')).toContain('<td');
	expect(renderMarkdown('| a |\n| b |')).toBe('<p>| a |</p><p>| b |</p>');
});
