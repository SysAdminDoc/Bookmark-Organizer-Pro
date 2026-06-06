#compdef bop
# zsh completion for bop (Bookmark Organizer Pro)
# Copy to a directory in your $fpath, e.g. ~/.zfunc/

_bop() {
    local -a commands
    commands=(
        'help:Show help and available commands'
        'list:List bookmarks'
        'add:Add a bookmark'
        'delete:Delete a bookmark'
        'search:Search bookmarks'
        'import:Import bookmarks from file'
        'export:Export bookmarks'
        'categories:List categories'
        'tags:List tags'
        'stats:Show statistics'
        'check:Check bookmark URLs'
        'ingest:Extract page content'
        'snapshot:Archive a page'
        'embed:Build vector embeddings'
        'semantic:Semantic search'
        'hybrid:Hybrid keyword+semantic search'
        'summarize:AI summary with citations'
        'chat:Conversational RAG'
        'ask:Single-turn RAG query'
        'lint-tags:Find tag issues'
        'dups:Detect duplicates'
        'scan:Dead-link scan'
        'digest:Daily digest'
        'flow:Manage research flows'
        'feed:Manage RSS feeds'
        'import-pocket:Import Pocket export'
        'import-readwise:Import Readwise CSV'
        'import-pinboard:Import Pinboard JSON'
        'import-instapaper:Import Instapaper CSV'
        'import-reddit:Import Reddit saved'
        'import-wallabag:Import Wallabag JSON'
        'import-arc:Import Arc Browser'
        'import-matter:Import Matter CSV'
        'import-zotero:Import Zotero RDF'
        'zip-export:Export bookmarks as ZIP'
        'encrypt:Encrypt a file'
        'decrypt:Decrypt a file'
        'read-later:Manage read-later queue'
        'api-server:Start the local API server'
        'mcp-server:Start the MCP server'
        'smart-collections:Manage smart collections'
        'nl-query:Natural language query'
        'obsidian-export:Export to Obsidian vault'
        'epub-export:Export as EPUB'
        'atom-export:Export as Atom feed'
        'json-feed:Export as JSON Feed'
        'zotero-export:Export as Zotero RDF'
    )

    if (( CURRENT == 2 )); then
        _describe 'command' commands
        return
    fi

    case "$words[2]" in
        import*|export|obsidian-export|epub-export|atom-export|json-feed|zotero-export|zip-export|encrypt|decrypt)
            _files
            ;;
        flow)
            local -a flow_cmds=('list' 'new' 'add' 'show' 'delete')
            _describe 'flow command' flow_cmds
            ;;
        feed)
            local -a feed_cmds=('list' 'add' 'fetch' 'remove')
            _describe 'feed command' feed_cmds
            ;;
        read-later)
            local -a rl_cmds=('add' 'next' 'done' 'list')
            _describe 'read-later command' rl_cmds
            ;;
        embed)
            _values 'model' '--model=default' '--model=nomic' '--model=minilm'
            ;;
    esac
}

_bop "$@"
