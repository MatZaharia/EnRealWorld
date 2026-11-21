# Quickstart

Start your agent in the repository root. Give it the prompt and the listed inputs. The prompts refer to the [EnRealWorld skill](../../src/enrealworld/skills/enrealworld/SKILL.md), which the agent uses to prepare and run the team.

For the CLI, copy the prompt into the `task` field and point `public` at the case's `public/` directory. Use an empty directory for the text-only prompt.

The prompts are adapted for use outside the original experiment environment.

| Case | Prompt | Input materials |
| --- | --- | --- |
| Laboratory, factory, and home | [One prompt for all three scenes](text/prompt.txt) | Text only |
| *Interior with the Artist's Easel* | [Prompt](studio/prompt.txt) | [Reference painting](studio/public/reference.png) |
| *House by the Railroad* | [Prompt](railroad/prompt.txt) | [Reference from MoMA](https://www.moma.org/collection/works/78330) |
| Yates House | [Prompt](yates/prompt.txt) | [All 3 sheets](yates/public/drawings/) |
| Charles Goodnight Ranch House | [Prompt](goodnight-ranch/prompt.txt) | [All 9 sheets](goodnight-ranch/public/drawings/) |
| El Morro Lighthouse | [Prompt](el-morro/prompt.txt) | [All 5 sheets](el-morro/public/drawings/) |

For *House by the Railroad*, obtain the reference from the museum and save it as `examples/quickstart/railroad/public/reference.jpg` before running the prompt. Create the `public/` directory if needed.

## Sources

- *Interior with the Artist's Easel*, Vilhelm Hammershøi, 1910, accession KMS7444. [SMK Open](https://open.smk.dk/en/artwork/image/KMS7444)
- *House by the Railroad*, Edward Hopper, 1925. [The Museum of Modern Art](https://www.moma.org/collection/works/78330)
- Measured drawings from the Library of Congress Historic American Buildings Survey. [Yates House](https://www.loc.gov/resource/hhh.tx1098.sheet?st=gallery), [Charles Goodnight Ranch House](https://www.loc.gov/resource/hhh.tx1056.sheet?st=gallery), [El Morro Lighthouse](https://www.loc.gov/resource/hhh.pr1465.sheet?st=gallery)
