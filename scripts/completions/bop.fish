# fish completion for bop (Bookmark Organizer Pro)
# Copy to ~/.config/fish/completions/bop.fish

set -l commands help list add delete search import export categories tags stats \
    check ingest snapshot embed semantic hybrid summarize chat ask lint-tags dups \
    scan digest flow feed import-pocket import-readwise import-pinboard \
    import-instapaper import-reddit import-wallabag import-arc import-matter \
    import-zotero zip-export encrypt decrypt read-later api-server mcp-server \
    smart-collections nl-query obsidian-export epub-export atom-export json-feed \
    zotero-export

complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a help -d 'Show help'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a list -d 'List bookmarks'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a add -d 'Add a bookmark'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a delete -d 'Delete a bookmark'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a search -d 'Search bookmarks'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a import -d 'Import from file'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a export -d 'Export bookmarks'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a categories -d 'List categories'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a tags -d 'List tags'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a stats -d 'Show statistics'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a check -d 'Check URLs'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a ingest -d 'Extract content'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a snapshot -d 'Archive page'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a embed -d 'Build embeddings'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a semantic -d 'Semantic search'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a hybrid -d 'Hybrid search'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a summarize -d 'AI summary'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a chat -d 'RAG chat'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a ask -d 'RAG query'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a lint-tags -d 'Find tag issues'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a dups -d 'Detect duplicates'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a scan -d 'Dead-link scan'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a digest -d 'Daily digest'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a flow -d 'Research flows'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a feed -d 'RSS feeds'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a import-pocket -d 'Import Pocket'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a import-readwise -d 'Import Readwise'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a import-pinboard -d 'Import Pinboard'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a import-instapaper -d 'Import Instapaper'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a import-reddit -d 'Import Reddit'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a import-wallabag -d 'Import Wallabag'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a import-arc -d 'Import Arc Browser'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a import-matter -d 'Import Matter'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a import-zotero -d 'Import Zotero'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a zip-export -d 'ZIP export'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a encrypt -d 'Encrypt file'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a decrypt -d 'Decrypt file'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a read-later -d 'Read-later queue'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a api-server -d 'Start API server'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a mcp-server -d 'Start MCP server'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a smart-collections -d 'Smart collections'
complete -c bop -f -n "not __fish_seen_subcommand_from $commands" -a nl-query -d 'Natural language query'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a obsidian-export -d 'Export to Obsidian'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a epub-export -d 'Export as EPUB'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a atom-export -d 'Export as Atom'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a json-feed -d 'Export JSON Feed'
complete -c bop -n "not __fish_seen_subcommand_from $commands" -a zotero-export -d 'Export Zotero RDF'

# Subcommand completions
complete -c bop -f -n "__fish_seen_subcommand_from flow" -a "list new add show delete"
complete -c bop -f -n "__fish_seen_subcommand_from feed" -a "list add fetch remove"
complete -c bop -f -n "__fish_seen_subcommand_from read-later" -a "add next done list"
complete -c bop -f -n "__fish_seen_subcommand_from embed" -a "--model=default --model=nomic --model=minilm"
