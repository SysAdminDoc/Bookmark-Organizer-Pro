# bash completion for bop (Bookmark Organizer Pro)
# Source this file: . bop.bash  OR copy to /etc/bash_completion.d/

_bop_completions() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local commands="help list add delete search import export categories tags stats \
check ingest snapshot embed semantic hybrid summarize chat ask lint-tags dups scan \
digest flow feed import-pocket import-readwise import-pinboard import-instapaper \
import-reddit import-wallabag import-arc import-matter import-zotero zip-export \
encrypt decrypt read-later api-server mcp-server smart-collections nl-query \
obsidian-export epub-export atom-export json-feed zotero-export"

    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        return 0
    fi

    local cmd="${COMP_WORDS[1]}"
    case "$cmd" in
        import|import-pocket|import-readwise|import-pinboard|import-instapaper|import-reddit|import-wallabag|import-arc|import-matter|import-zotero)
            COMPREPLY=( $(compgen -f -- "$cur") )
            ;;
        export|obsidian-export|epub-export|atom-export|json-feed|zotero-export|zip-export)
            COMPREPLY=( $(compgen -f -- "$cur") )
            ;;
        flow)
            COMPREPLY=( $(compgen -W "list new add show delete" -- "$cur") )
            ;;
        feed)
            COMPREPLY=( $(compgen -W "list add fetch remove" -- "$cur") )
            ;;
        read-later)
            COMPREPLY=( $(compgen -W "add next done list" -- "$cur") )
            ;;
        embed)
            COMPREPLY=( $(compgen -W "--model=default --model=nomic --model=minilm" -- "$cur") )
            ;;
    esac
    return 0
}

complete -F _bop_completions bop
