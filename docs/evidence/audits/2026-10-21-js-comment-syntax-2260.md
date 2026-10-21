# Audit: JavaScript comment syntax, ECMA-262 (claude-skills #2260)

**Verifier.** The real `doctrine-verifier`, run on 2026-10-21 for #2260 against the living ECMA-262 (the page reads "Draft ECMA-262 / October 16, 2026"), quoting from the page's raw text. Every quote was then re-matched by `python3 scripts/check_verdict_quotes.py` (19 phrases, all on their pages). Where the specification states a fact only through its grammar, the note says so: those verdicts are CONFIRMED by grammar, not by a prose sentence.

**What this decides for rails-stack's `security.code_syntax` row (`.js`, `.mjs`, `.cjs`).** C1 and C2 are the neutral `/* */` and `//` rules, declared for the row. C3: the hashbang is the neutral `#` line marker, line 1 only. C4: `<!--` and `-->` at the start of a line are never code (a comment in a Script, a syntax error in a Module), so they are the row's `line_comments`; `<!--` after other text is a comment in a Script and code in a Module, so it is a `refuse_when`. C5: a template literal's body is not code and this reader has no tokenizer, so a line with an odd number of backticks is a `refuse_when`. C6: `//` and `/*` can appear inside a regex literal via a class or an escape, and a line is read as a comment only when it starts with the marker, so a regex line is code. C7 (JSX, TypeScript) is INCONCLUSIVE: `.ts`, `.jsx` and `.tsx` stay undeclared and refused, and a `{/*` (a JSX comment container) in a `.js` file is a `refuse_when`.

Source: https://tc39.es/ecma262/ , Draft ECMA-262 / October 16, 2026. Quotes matched against the normalised page text.

## C1. MultiLineComment is /* ... */ and does not nest (12.4)
Verdict: CONFIRMED [quotes: C1]

```quotes C1
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.4 Comments) | MultiLineComment :: /* MultiLineCommentCharsopt */
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.4 Comments) | Multi-line comments cannot nest.
```

## C2. SingleLineComment excludes the LineTerminator; a MultiLineComment with a line terminator acts as one (12.4)
Verdict: CONFIRMED [quotes: C2]

```quotes C2
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.4 Comments) | SingleLineCommentChar :: SourceCharacter but not LineTerminator
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.4 Comments) | a single-line comment always consists of all code points from the // marker to the end of the line
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.4 Comments) | the LineTerminator at the end of the line is not considered to be part of the single-line comment
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.4 Comments) | if a MultiLineComment contains a line terminator code point, then the entire comment is considered to be a LineTerminator for purposes of parsing by the syntactic grammar
```

## C3. HashbangComment: #! then single-line comment characters, only at the start of a Script or Module (12.5, 12.6 intro)
Verdict: CONFIRMED [quotes: C3]
Note: the spec has no sentence saying "not on a later line". It says the comment is location-sensitive and that the goal symbol producing it is used only at the start of a Script or Module; every later position uses a goal without HashbangComment.

```quotes C3
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.5 Hashbang Comments) | HashbangComment :: #! SingleLineCommentCharsopt
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.5 Hashbang Comments) | Hashbang Comments are location-sensitive
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12 ECMAScript Language: Lexical Grammar) | The InputElementHashbangOrRegExp goal is used at the start of a Script or Module.
```

## C4. Annex B HTML-like comments, not allowed for Module (B.1.1)
Verdict: CONFIRMED [quotes: C4]
Note: "begins a line" is carried by the grammar (HTMLCloseComment is WhiteSpaceSequence and comments, then `-->`, reached after a LineTerminatorSequence or at input start), not a prose sentence.

```quotes C4
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (B.1.1 HTML-like Comments) | this extension is not allowed when parsing source text using the goal symbol Module
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (B.1.1 HTML-like Comments) | SingleLineHTMLOpenComment :: <!-- SingleLineCommentCharsopt
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (B.1.1 HTML-like Comments) | HTMLCloseComment :: WhiteSpaceSequenceopt SingleLineDelimitedCommentSequenceopt --> SingleLineCommentCharsopt
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (B.1.1 HTML-like Comments) | SingleLineHTMLCloseComment :: LineTerminatorSequence HTMLCloseComment
```

## C5. Template literal characters are TemplateCharacters, not comment text (12.9.6)
Verdict: CONFIRMED [quotes: C5]
Note: the spec has no sentence saying "// does not start a comment in a template". It follows from the grammar: a Template is made of TemplateCharacters, each any SourceCharacter except `, \, $ or LineTerminator, so / and * are plain TemplateCharacters. Inside `${ }` the text is ordinary code and comments apply there.

```quotes C5
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.9.6 Template Literal Lexical Components) | NoSubstitutionTemplate :: ` TemplateCharactersopt `
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.9.6 Template Literal Lexical Components) | SourceCharacter but not one of ` or \ or $ or LineTerminator
```

## C6. Regular expression literal body (12.9.5)
Verdict: CONFIRMED [quotes: C6]
Note: there is no prose sentence about `/` in a class. The grammar says it: RegularExpressionChar excludes `/` but admits a RegularExpressionClass, whose RegularExpressionClassChar excludes only `]` and `\`. The first char excludes `*`, `\`, `/`, `[` (a `\` or `[` start is re-admitted via the backslash sequence or class alternatives). Note 2 covers `//`.

```quotes C6
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.9.5 Regular Expression Literals) | RegularExpressionFirstChar :: RegularExpressionNonTerminator but not one of * or \ or / or [
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.9.5 Regular Expression Literals) | RegularExpressionChar :: RegularExpressionNonTerminator but not one of \ or / or [
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.9.5 Regular Expression Literals) | RegularExpressionClassChar :: RegularExpressionNonTerminator but not one of ] or \
https://tc39.es/ecma262/ | Draft ECMA-262 / October 16, 2026 (12.9.5 Regular Expression Literals) | the code unit sequence // starts a single-line comment
```

## C7. JSX and TypeScript comments
Verdict: INCONCLUSIVE
The string "JSX" and the string "TypeScript" occur nowhere in the page text (searched the normalised text). ECMA-262 does not cover them; they are outside this specification. Evidence needed: the JSX spec (facebook.github.io/jsx) and the TypeScript handbook/spec for the version in use.
