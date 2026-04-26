set dotenv-load := true
set shell := ["bash", "-lc"]

extension := "/Users/twhitehurst3/Documents/twhitehurst3/Studying/Projects/lead-agents/apps/multi-team-chat/extensions/multi-team-chat.ts"

default:
    @just --list

# Launch Multi-Team Chat with the default team config
team:
    pi -e {{extension}}

# Launch Multi-Team Chat with a custom config file (path relative to project root)
# Usage: just teamc .pi/multi-team/engineering-config.yaml
teamc config:
    pi -e {{extension}} --team {{config}}

# Launch Engineering-only team
team-eng:
    pi -e {{extension}} --team .pi/multi-team/engineering-config.yaml

# Launch Planning + Engineering team
team-pe:
    pi -e {{extension}} --team .pi/multi-team/planning-and-engineering-config.yaml

# Launch Planning + 3x Scaled Engineering teams
team-scale:
    pi -e {{extension}} --team .pi/multi-team/plan-and-scale-engineering-config.yaml

# Launch Open-source / multi-provider team (diverse models)
team-oss:
    pi -e {{extension}} --team .pi/multi-team/opensource-team-config.yaml

# List all available team configs
team-list:
    pi -e {{extension}} --list
