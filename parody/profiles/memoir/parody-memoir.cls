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
\renewcommand{\chaptermark}[1]{\markboth{\thechapter.\ #1}{}}
\renewcommand{\sectionmark}[1]{\markright{\thesection\ \ #1}}
\makepsmarks{parody}{}% marks set by \chaptermark/\sectionmark above
\aliaspagestyle{chapter}{plain}
\pagestyle{parody}

% ---- chapter opener: large bold number, then large bold title ----------
\makechapterstyle{parody}{%
  \setlength{\beforechapskip}{10pt}%
  \setlength{\midchapskip}{12pt}%
  \setlength{\afterchapskip}{2.2\onelineskip}%
  \renewcommand*{\chapnamefont}{\normalfont\large\scshape}%
  \renewcommand*{\chapnumfont}{\normalfont\fontsize{52}{54}\selectfont\bfseries}%
  \renewcommand*{\chaptitlefont}{\normalfont\Large\bfseries\raggedright}%
  \renewcommand*{\printchaptername}{}%
  \renewcommand*{\chapternamenum}{}%
  \renewcommand*{\printchapternum}{{\color{parodyaccent}\chapnumfont\thechapter}}%
  \renewcommand*{\afterchapternum}{\par\nobreak\vskip\midchapskip}%
  \renewcommand*{\printchaptertitle}[1]{\chaptitlefont ##1}%
}
\chapterstyle{parody}

% ---- section heads: bold, bold math (an MIT touch), ragged right -------
\setsecheadstyle{\normalfont\large\bfseries\boldmath\raggedright}
\setsubsecheadstyle{\normalfont\normalsize\bfseries\raggedright}
\setsubsubsecheadstyle{\normalfont\normalsize\itshape\raggedright}
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
\renewcommand{\cftsectionleader}{\hspace*{1.5em}}
\renewcommand{\cftsubsectionleader}{\hspace*{1.5em}}
\setlength{\cftbeforechapterskip}{0.6\onelineskip}

% ---- title page: restrained, ragged-right ------------------------------
\pretitle{\vspace*{\fill}\begin{flushright}\Huge\bfseries}
\posttitle{\par\end{flushright}\vskip 1.5em}
\preauthor{\begin{flushright}\Large}
\postauthor{\par\end{flushright}}
\predate{\begin{flushright}\large}
\postdate{\par\end{flushright}\vspace*{\fill}}

\endinput
