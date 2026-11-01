# Measured tests paid with API credit (1 November 2026)

Do these tools really help, or does it only feel that way? To find out, each tool was tried on the same tasks with it and
without it, in fresh agents, paid with API credit so every cost is an exact number. All the tests of that day are here,
including those that went badly.

**How they ran.** Claude Code with none of the author's rules, hooks or plugins (`claude -p`), model Sonnet 5.5, usually 3
repetitions per side. The one exception is the last test, which called the model directly. "Steps" are calls to the model.
The agent that ran the tests also wrote the questions and graded the answers, so a good grade is weaker evidence than a
good cost figure.

**What it cost.** The test runs: **$51.28** (the sum of the seven tables of runs). The sessions that prepared the tests, ran
them and analysed them: **$47.55**, from their own records. Together **$98.83**.

| Test | Runs | Cost of the runs |
|---|---|---|
| 1. First round: four tools, with and without | 78 | $6.00 |
| 2. Five versions of Quotient compared | 69 | $6.82 |
| 3. The fix for small jobs (1.3.4) | 54 | $14.81 |
| 4. Screen recorder: a short text summary next to the frames | 48 | $1.56 |
| 5. Second round: normal use, big jobs, the recorder again | 74 | $12.78 |
| 6. Long texts: why they were quoted too low (1.3.5) | 11 | $5.27 |
| 7. Do skills start by themselves? | 843 | $4.04 |

Certainty below uses four words: **solid**, **medium**, **weak**, **unknown**. Most results are weak: few repetitions, small
jobs, one model.

## 1. First round: four tools

### Psyche Map

10 questions about work facts. With [Psyche Map](https://github.com/Korvonordico/psyche-map): the map, its skill and two
plain files. Without: only the two plain files.

| | Mean cost | Time | Steps | Right answers |
|---|---|---|---|---|
| With the map | $0.26 | 75 s | 19 | 9.5 of 10 |
| Without | $0.05 | 17 s | 4 | 2.5 of 10 |

It helps, and it costs about 5 times more and takes 4 times as long. **Solid** for facts that are only in the map. Weak
points: the questions were chosen by looking at the map, and 8 of 10 had their answer only there, so this measures whether
the agent finds what is there, not how often the map is needed. Once it missed a fact that was there. Without the map the
agent never made anything up: it said "not found".

### Quotient 1.3.3 on small jobs

4 small jobs (code, a README, web research, sorting 40 files). With the plugin: a quote, then the job. Without: "how many
tokens will it cost?", then the job.

| | Mean cost | Of which the quote | Time | Steps | Typical miss | Within ±30% |
|---|---|---|---|---|---|---|
| With Quotient | $0.16 | $0.05 | 59 s | 11 | 30% | 6 of 11 |
| Without | $0.10 | $0.02 | 35 s | 8 | 64% | 4 of 12 |

**A bad result:** better estimates (weak), but the job cost 67% more, and 4 jobs of 11 went unmeasured. The 67% was itself
too high: the test added up the two parts of a resumed session, and a resumed session already reports its whole cost.
Measured again in test 3, the extra cost was 47%. One job also hung for 12 minutes on a search of the whole disk, not
Quotient's fault, and was left out of the means.

### Screen recorder ([Iris Insight](https://github.com/Korvonordico/iris-insight))

5 problems from a game's real recordings. With: 25 frames in one image. Without: the same 25 frames as separate images.

| | Mean cost | Time | Steps | Right |
|---|---|---|---|---|
| Frames in one image | $0.027 | 7 s | 2 | 87% |
| Separate images | $0.040 | 15 s | 11 | 80% |

It helps a little: 30% cheaper and twice as fast, with similar quality. **Weak**: 5 problems. The saving comes from fewer
steps, not from the image. Neither way could tell a long loading from a freeze, or see a slowdown: test 4 goes after that.

### Two community coding skills

[ponytail](https://github.com/DietrichGebert/ponytail) and systematic-debugging (Hermes Agent's version of the one in [superpowers](https://github.com/obra/superpowers)).

2 easy tasks on a copy of a real piece of Quotient, checked with hidden tests.

| | Mean cost | Time | Steps | Checks passed |
|---|---|---|---|---|
| Skills installed | $0.044 | 19 s | 6 | 100% |
| No skills | $0.044 | 19 s | 6 | 100% |
| Skills called by name | $0.068 | 22 s | 11 | 100% |

**No difference. Solid, but only for easy tasks.** Installed, the skills never started by themselves (0 of 6). Called by
name they cost 55% more on average, for a slightly better test. A hard problem might change this: not tried.

## 2. Five versions of Quotient

3 new small jobs, 3 times each, per version. Every version started from nothing, as a new user. All 63 jobs passed the
checks: versions change the cost and the estimate, not the result.

| | Mean cost | Of which the quote | Steps | Time | Typical miss | The estimate is usually | Within ±30% | Measured |
|---|---|---|---|---|---|---|---|---|
| Only the job, no plugin | $0.041 | - | 4 | 17 s | - | - | - | - |
| Spoken estimate, no plugin | $0.079 | $0.024 | 6 | 24 s | 149% | 2.5x too high | 0 of 9 | - |
| 0.2.0 | $0.096 | $0.032 | 6 | 36 s | 395% | 5x too high | 0 of 7 | 8 of 9 |
| 0.9.7 | $0.096 | $0.031 | 6 | 34 s | 348% | 4.5x too high | 0 of 9 | 9 of 9 |
| 1.1.8 | $0.122 | $0.042 | 8 | 40 s | 57% | 1.6x too high | 2 of 9 | 7 of 9 |
| 1.3.2 | $0.146 | $0.052 | 11 | 43 s | 93% | a little low (real 1.2x) | 3 of 9 | 6 of 9 |
| 1.3.3 | $0.144 | $0.052 | 10 | 43 s | 89% | low (real 1.7x) | 0 of 9 | 6 of 9 |

What it showed, good and bad:

- **On jobs this small, the quote cost more than the job itself.** Against an agent's spoken estimate the plugin added 22%
  (0.2.0, 0.9.7), 56% (1.1.8) and 85% (1.3.x). This is what test 3 fixed.
- **Newer was not simply better.** The closest totals were 1.1.8's, by accident: its work estimate was about 4 times too high,
  and it hardly counted the fixed part of a job. 0.2.0 and 0.9.7 were worse than an agent guessing alone.
- **1.3.2 and 1.3.3 have the same quoting code**, and got 3 of 9 and 0 of 9 within ±30%. So differences of that size are luck.
- Each version's numbers are only 9 jobs (**weak**), all far below the threshold Quotient is built for.

## 3. The fix for small jobs (1.3.4)

Full causes: [small-jobs.md](small-jobs.md). 4 small jobs, 3 times each, per side:

| | Mean cost | Of which the quote | Against no plugin | Typical miss | Within ±30% | Measured |
|---|---|---|---|---|---|---|
| 1.3.4 | $0.082 | $0.031 | +9% | 31% | 5 of 12 | 12 of 12 |
| 1.3.3 | $0.110 | $0.052 | +47% | 35% | 5 of 12 | 5 of 12 |
| No plugin | $0.075 | $0.022 | - | 277% | 0 of 12 | - |

From +47% to +9%: **solid** for the cause (seen call by call), **medium** for the number. Accuracy about the same: **weak**,
3 jobs per type. Code is still quoted about twice too high, and this was left alone: 3 jobs are too few to correct on.

## 4. Screen recorder: a short summary next to the frames

Same kind of test as in round one, with a text summary of about 400 tokens added:

| | Mean cost | Time | Steps | Right |
|---|---|---|---|---|
| Frames + summary | $0.030 | 9 s | 3 | 97% |
| Frames alone | $0.027 | 9 s | 2 | 80% |
| Separate images | $0.041 | 16 s | 11 | 73% |

It helps: the freeze was called a freeze 3 times of 3 (0 of 3 with frames alone), the slowdown seen 3 of 3 (0 of 6 without
a summary). **Weak**: 5 problems, and the summaries were rebuilt from old recordings. **A bad first run:** the summary said
"same image for 10 seconds" because writing the recording itself had paused the clock, all 3 answers said "freeze", and the
new method scored 77%, worse than frames alone. Fixed and run again. On a broken-drawing problem the summary did not help (2
of 3 against 3 of 3).

## 5. Second round

### Quotient in normal use

The user gives a medium job and says nothing about cost: 3 jobs, twice each.

| | Mean cost | Time | Steps | Quotes given | Jobs measured |
|---|---|---|---|---|---|
| Quotient 1.3.4 | $0.294 | 123 s | 18 | 0 of 6 | 0 of 6 |
| Without | $0.263 | 104 s | 17 | - | - |

**No real difference in cost; weak** (2 runs per job). The text Quotient adds was 1,300 to 1,700 weighted tokens a job, about
1%; the rest of the 13% is the jobs' own variation. **Two weak points:** medium jobs under the threshold are not measured (0
of 6), which is by design but means Quotient learns nothing from them. And in 1 job of 6 the agent wrote its quote at the end
of a job already done, which opened a job never closed (fixed: see the CHANGELOG).

### Quotient on big jobs

A package of code and a guide of 10,000 words, 10 jobs per side:

| | Mean cost | Of which the quote | Typical miss | Within ±30% | Measured |
|---|---|---|---|---|---|
| Quotient 1.3.4 | $0.82 | $0.046 | 40% | 4 of 10 | 10 of 10 |
| Without | $0.72 | $0.026 | 192% | 2 of 10 | - |

**It helps with estimates and measure** (**solid** on the measure, **weak** on the numbers), **and costs 14% more** (**weak**).
The quote is only $0.02 of that; the rest came from more steps (35 against 28), maybe because the test says "the biggest
level", maybe chance. Without Quotient the agent quoted the guide at 40,000 to 80,000 tokens and it cost 450,000 to 670,000.
With it the guide was still quoted at about half its cost: that is test 6.

### Screen recorder, on 9 new problems

| | Mean cost | Time | Steps | Right |
|---|---|---|---|---|
| Frames + summary | $0.031 | 7.5 s | 3 | 89% |
| Separate images | $0.034 | 11.4 s | 8 | 46% |

It helps a lot on freezes (9 of 9 against 0 of 9) and on a slowdown in the arena (3 of 3 against 0 of 3): **solid**, because the
difference comes from the kind of data. **Weak** on the percentage: 9 chosen cases, nearly all faked by test commands, graded
by the agent that ran the test. **Where it did badly:** a slowdown on a static screen (0.5 of 3, worse than images at 1 of 3), and all 3 summaries
explained a black screen as "stuck loading", misled by a single disk read. A broken drawing and a long loading could not be tried.

## 6. Long texts (1.3.5)

Quotient counted 27 weighted tokens per word. Every text from 2,000 words up cost more: 14 of 14, between 32 and 63 per word
asked, about 43 in the middle. The change: **40 per word**.

Real cost / quote (1 = right, above 1 = cost more than quoted):

| Words asked | 1.3.4 | With 40, same jobs recomputed | With 40, new runs |
|---|---|---|---|
| 400 | 1.05 to 1.31 (middle 1.16) | 0.84 to 1.05 (0.93) | 0.91 |
| 2,000 | 0.59, 1.17 | 0.50, 0.92 | 1.20 |
| 5,000 | 1.35, 1.36 | 0.95, 0.98 | - |
| 10,000 | 0.92 to 2.15 (1.71) | 0.74 to 1.51 (1.19) | 1.36 |
| 20,000 | 1.05 | 0.79 | - |
| **All** | typical miss **31%** | typical miss **19%** | - |

**Solid** on the cause and the direction, **weak** on the number: only one new run per length, 40 was chosen on the same data
it is measured on, and the same 10,000-word job cost from 379,000 to 711,000 weighted tokens. One model, one kind of text. The
agent also writes more than asked, up to 90% more, which Quotient cannot know beforehand. Code and other kinds of work are not
touched by this. A variant (34 per word plus 1 per 1,000 words) was thrown out: real runs quoted short texts at about twice
their cost.

## 7. Do skills start by themselves?

10 skill descriptions of Hermes Agent were rewritten with the words the user really says, and the model was asked to pick the
right skill before and after: 843 attempts, a direct call to the model with Hermes' list of skills and instructions, 5
repetitions before and 3 after.

| | Right loads | Wrong loads | False starts |
|---|---|---|---|
| Easy requests, before | 150 of 150 | 29 | 0 of 25 |
| Easy requests, after | 90 of 90 | 7 | 0 of 15 |
| Hard requests, before | 80 of 100 | 21 | 0 of 25 |
| Hard requests, after | 60 of 60 | 5 | 0 of 15 |

**Medium** on the test bench, **weak** for real use. It is a simulation (5 tools instead of about 40, no memory), and the
descriptions were rewritten while looking at the failures of the same requests. The cost is an upper estimate at high prices.
A first version with game names in it made things worse, loading the wrong skill 10 times of 15, and was corrected.
This says nothing about Claude Code, where installed skills did not start at all in test 1.
