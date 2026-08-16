% parody foundational print class — a clean book design on top of `memoir`.
%
% This is the portable, batteries-included counterpart of a publisher's house
% class (e.g. MIT Press's NewMath_MIT). It borrows that design's sensibilities
% — a big-number chapter opener, tight italic running heads, no-leader-dots TOC,
% a Palatino-family body — without cloning any one publisher's spec, and gets
% page geometry, chapter styles, epigraphs, and front matter from memoir as
% first-class features rather than hand-rolled patches.
%
% Colours and fonts live in a separate, swappable parody-theme-*.sty so a book
% can re-skin without forking the class. Custom environments emitted by
% parody/filters/print.lua live in parody-environments.sty (the profile
% contract). This file owns page design only.
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{parody-memoir}[2026/06/26 parody foundational memoir-based book class]

% ---- trim size (stock = trimmed; print houses add their own bleed) ----
\newcommand{\parody@stockh}{9in}
\newcommand{\parody@stockw}{6in}
\DeclareOption{6x9}{\renewcommand\parody@stockh{9in}\renewcommand\parody@stockw{6in}}
\DeclareOption{7x10}{\renewcommand\parody@stockh{10in}\renewcommand\parody@stockw{7in}}
\DeclareOption{letter}{\renewcommand\parody@stockh{11in}\renewcommand\parody@stockw{8.5in}}
% font size, oneside/twoside, draft, ... pass straight through to memoir
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{memoir}}
\ProcessOptions\relax
\LoadClass{memoir}

% ---- page layout -------------------------------------------------------
\setstocksize{\parody@stockh}{\parody@stockw}
\settrimmedsize{\stockheight}{\stockwidth}{*}
\settrims{0pt}{0pt}
% Inner (spine) margin larger than outer for binding; memoir derives the
% text block from these plus the head/foot allowance below.
\setlrmarginsandblock{0.95in}{0.75in}{*}
\setulmarginsandblock{0.85in}{*}{1.45}
\setheadfoot{\onelineskip}{2\onelineskip}
\setheaderspaces{*}{1.6\onelineskip}{*}
\checkandfixthelayout

% ---- headings are title case, mechanically ------------------------------
% Sections are authored in sentence case ("Voltage, current, resistance, and
% all that"); the house style sets them in title case. titlecaps does the
% capitalising so an author never has to think about it, and it carries no
% default list of words to leave alone — hence the list below. \titlecap is
% applied as the LAST macro of a heading style, which is memoir's documented
% idiom for "hand the heading text to this one-argument command".
\RequirePackage{titlecaps}
% titlecaps recurses into \textit, \textbf and \texttt so their contents get
% cased along with everything else — but it has no case for \emph, which is
% exactly what pandoc emits for *emphasis*. An unhandled macro is not skipped,
% it is mangled: "Algebra \emph{ex nihilo}" set only the "e" italic and
% doubled the space before it.
%
% So the \emph TOKENS are swapped for \textit before casing. Teaching titlecaps
% about \emph directly does not work — \emph is robust, and giving it \textit's
% internal treatment duplicated and reordered the trailing words ("Algebra
% \emph{ex nihilo} and beyond" came out "and beyond and beyond and
% beyondAlgebra Ex Nihilo"). Inside a heading the two are interchangeable: they
% differ only in how they nest, and a heading is never already italic.
\ExplSyntaxOn
\NewDocumentCommand{\parodytitlecap}{m}{
  \tl_set:Nn \l__parody_tc_tl {#1}
  \tl_replace_all:Nnn \l__parody_tc_tl { \emph } { \textit }
  \exp_args:NV \titlecap \l__parody_tc_tl
}
\tl_new:N \l__parody_tc_tl
\ExplSyntaxOff
% Articles, coordinating conjunctions and short prepositions only. Verbs stay
% capitalised even when short ("Is", "Are", "Be"), which is why they are not
% on this list.
\Addlcwords{a an the and but or nor for so yet at by in of on to up via as
  from into onto over with}

% Accent colour for structural flourishes (the chapter number). A theme's
% parody-theme-*.sty redefines parodyaccent; this \providecolor keeps the class
% standalone if loaded without one.
\RequirePackage{xcolor}
\providecolor{parodyaccent}{HTML}{1F4E79}

% ---- running heads: page | chapter (even), section | page (odd) --------
% Small italic marks, MIT-house feel, no rule.
\nouppercaseheads
\makepagestyle{parody}
\makeevenhead{parody}{\small\thepage}{}{\small\itshape\leftmark}
\makeoddhead{parody}{\small\itshape\rightmark}{}{\small\thepage}
\makeevenfoot{parody}{}{}{}
\makeoddfoot{parody}{}{}{}
\renewcommand{\chaptermark}[1]{\markboth{\thechapter.\ \parodytitlecap{#1}}{}}
\renewcommand{\sectionmark}[1]{\markright{\thesection\ \ \parodytitlecap{#1}}}
\makepsmarks{parody}{}% marks set by \chaptermark/\sectionmark above
\aliaspagestyle{chapter}{plain}
\pagestyle{parody}

% ---- chapter opener ----------------------------------------------------
%   CHAPTER                                                              1
%   ═══════════════════════════════════════════════════════════════════════
%   Fundamentals
%
% The numeral and the rule align to the measure — nothing crosses into the
% margin. \parody@chapbleed is the knob: set it to a positive length and both
% overhang by that much, built by setting a box WIDER than \textwidth inside a
% \makebox that is exactly \textwidth, so TeX's idea of the line width is
% unchanged either way.
\newlength{\parody@chapbleed}
\setlength{\parody@chapbleed}{0pt}
% \textls comes from microtype (loaded by the theme). Keep the class usable
% on its own: fall back to no letterspacing if the theme is absent.
\AtBeginDocument{\providecommand{\textls}[2][]{#2}}

\newcommand{\parody@chapopener}[1]{%
  \noindent\makebox[\textwidth][l]{%
    \makebox[\dimexpr\textwidth+\parody@chapbleed\relax][s]{%
      {\chapnamefont\color{parodyaccent}\textls[350]{\@chapapp}}%
      \hfill
      \smash{\raisebox{-0.2\height}{{\chapnumfont\color{parodyaccent}#1}}}%
    }%
  }\par\nobreak}

\newcommand{\parody@chaprule}{%
  \par\nobreak\vskip 6pt
  \noindent\makebox[\textwidth][l]{%
    {\color{parodyaccent}%
     \rule{\dimexpr\textwidth+\parody@chapbleed\relax}{2pt}}}%
  \par\nobreak\vskip 0.8\onelineskip}

\makechapterstyle{parodygraphic}{%
  \setlength{\beforechapskip}{6pt}%
  \setlength{\midchapskip}{0pt}%
  \setlength{\afterchapskip}{2.4\onelineskip}%
  \renewcommand*{\chapnamefont}{\normalfont\footnotesize\scshape}%
  \renewcommand*{\chapnumfont}{\normalfont\fontsize{80}{80}\selectfont\bfseries}%
  \renewcommand*{\chaptitlefont}{\normalfont\HUGE\bfseries\raggedright}%
  \renewcommand*{\printchaptername}{}%
  \renewcommand*{\chapternamenum}{}%
  \renewcommand*{\printchapternum}{\parody@chapopener{\thechapter}}%
  \renewcommand*{\afterchapternum}{}%
  % The rule lives with the title, not the number, so an unnumbered chapter
  % (Contents, Bibliography) still opens under it.
  \renewcommand*{\printchaptertitle}[1]{%
    \parody@chaprule\chaptitlefont\parodytitlecap{##1}}%
}
\chapterstyle{parodygraphic}

% ---- section heads: bold, bold math (an MIT touch), ragged right -------
\setsecheadstyle{\normalfont\large\bfseries\boldmath\raggedright\parodytitlecap}
\setsubsecheadstyle{\normalfont\normalsize\bfseries\raggedright\parodytitlecap}
\setsubsubsecheadstyle{\normalfont\normalsize\itshape\raggedright\parodytitlecap}
\setbeforesecskip{-1.2\onelineskip plus -.4\onelineskip minus -.2\onelineskip}
\setaftersecskip{0.6\onelineskip plus .2\onelineskip}
% Number down to subsubsection, but list only to subsection: the deepest heads
% carry a number for the reader and for cross-references, without a third tier
% swelling the contents (#576).
\setsecnumdepth{subsubsection}
\settocdepth{subsection}

% ---- table of contents: bold chapters, no leader dots ------------------
\renewcommand{\cftchapterfont}{\bfseries}
\renewcommand{\cftchapterpagefont}{\bfseries}
\renewcommand{\cftchapterleader}{\hfill}
\renewcommand{\cftchapterafterpnum}{}
% \hfill, not a fixed \hspace: a fixed skip leaves the line with no
% stretchable glue, so TeX stretches the interword space of the entry title
% instead ("Voltage,   current,   resistance,   and   all   that   1").
\renewcommand{\cftsectionleader}{\hfill}
\renewcommand{\cftsubsectionleader}{\hfill}
\setlength{\cftbeforechapterskip}{0.6\onelineskip}
% The contents is written from the authored (sentence-case) argument, so it is
% title-cased on the way INTO the .toc — not on the way out. By the time an
% entry reaches \l@<level> hyperref has wrapped it in \hyperlink, so titlecap
% would see a macro rather than words and do nothing. \protect keeps the cased
% call from expanding as the line is written; it runs when the .toc is read
% back (\@starttoc reads it under \makeatletter, so @-names are safe).
% Deferred to \AtBeginDocument because hyperref redefines \addcontentsline
% itself, and it loads after this class. Restricted to the toc: figure and
% table captions travel through here too, and they are not title case.
%
% The entry arrives as "\numberline{1.1}Title" (chapters:
% "\chapternumberline{1}Title"). The number must be held OUT of titlecap: it
% collapses the \numberline box, and that box is what sets the gap after the
% number and the hanging indent a wrapped entry falls back to — run it through
% and the title butts against its own number and long entries collide with it.
\def\parody@tc@num\numberline#1#2\parody@tc@end{\numberline{#1}\parodytitlecap{#2}}
\def\parody@tc@chap\chapternumberline#1#2\parody@tc@end{%
  \chapternumberline{#1}\parodytitlecap{#2}}
\def\parody@tc@plain#1\parody@tc@end{\parodytitlecap{#1}}
\def\parody@tc@sniff{%
  \@ifnextchar\numberline{\parody@tc@num}{%
    \@ifnextchar\chapternumberline{\parody@tc@chap}{\parody@tc@plain}}}
% Robust, and disabled inside PDF strings. hyperref expands each toc entry a
% second time to build the bookmark, and a fragile macro breaks there: the
% \@ifnextchar sniff falls apart and \parody@tc@end — a delimiter that is
% never \def'ed — is left to execute, one "Undefined control sequence" per
% heading. Bookmarks carry the plain title; casing is a typographic matter.
\DeclareRobustCommand{\parody@tcentry}[1]{\parody@tc@sniff#1\parody@tc@end}
\AtBeginDocument{%
  \providecommand{\pdfstringdefDisableCommands}[1]{}%
  \pdfstringdefDisableCommands{%
    \let\parody@tcentry\@firstofone
    \let\parodytitlecap\@firstofone
    \let\titlecap\@firstofone}}

\def\parody@toclist{toc}
% Defined at top level, not inside the hook: parameter tokens do not survive
% \AtBeginDocument intact, and writing the replacement there silently produced
% a .toc with no entries at all.
\newcommand{\parody@acl}[3]{%
  \def\parody@acl@file{#1}%
  \ifx\parody@acl@file\parody@toclist
    \parody@addcontentsline{#1}{#2}{\protect\parody@tcentry{#3}}%
  \else
    \parody@addcontentsline{#1}{#2}{#3}%
  \fi}
\AtBeginDocument{%
  \let\parody@addcontentsline\addcontentsline
  \let\addcontentsline\parody@acl}

% ---- title page: centred, folio-free, under the house rule -------------
\aliaspagestyle{title}{empty}
% memoir's \maketitle does not end the page, and \tableofcontents* opens its
% chapter head without a \clearpage — so without this the contents lands on
% the title page (and takes the chapter page style's folio with it).
% hooka runs on the title page itself. The \aliaspagestyle above is not
% enough on its own — memoir applies \thispagestyle{title} too late for it
% to beat the running head already set for the page.
\renewcommand{\maketitlehooka}{\thispagestyle{empty}}
\renewcommand{\maketitlehookd}{\clearpage}
\pretitle{\vspace*{0.22\textheight}\begin{center}\Huge\bfseries}
\posttitle{\par\end{center}\vskip 0.9em
  \begin{center}{\color{parodyaccent}\rule{0.38\textwidth}{2pt}}\end{center}
  \vskip 1.6em}
\preauthor{\begin{center}\Large}
\postauthor{\par\end{center}\vspace*{\fill}}
\predate{\begin{center}\large}
\postdate{\par\end{center}}

\endinput
