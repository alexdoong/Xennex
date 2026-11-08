using System;
using System.Collections.Generic;
using System.IO;
using System.Globalization;
using System.Linq;
using Microsoft.Data.Sqlite;
using Xennex.Models.Assets;
using Xennex.Services.Assets.Metadata;

namespace Xennex.Services.Assets;

internal sealed class AssetStore
{
    private readonly object gate = new();
    private readonly string database;

    public AssetStore(string directory)
    {
        Directory.CreateDirectory(directory);
        database = Path.Combine(directory, "library.db");
        using var connection = Open();
        using var command = connection.CreateCommand();
        command.CommandText = """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS roots(id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS assets(
              id TEXT PRIMARY KEY, root_id TEXT NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
              relative_path TEXT NOT NULL, parent_path TEXT NOT NULL, name TEXT NOT NULL,
              is_directory INTEGER NOT NULL, is_image INTEGER NOT NULL, available INTEGER NOT NULL,
              size INTEGER NOT NULL, modified_utc INTEGER NOT NULL, scan_id TEXT NOT NULL,
              width INTEGER NOT NULL DEFAULT 0, height INTEGER NOT NULL DEFAULT 0,
              favorite INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '', metadata TEXT NOT NULL DEFAULT '',
              UNIQUE(root_id, relative_path));
            CREATE INDEX IF NOT EXISTS assets_parent ON assets(root_id,parent_path,name,id);
            CREATE INDEX IF NOT EXISTS assets_name ON assets(name,id);
            CREATE INDEX IF NOT EXISTS assets_metadata_gallery ON assets(available,root_id,name,id)
              WHERE is_image=1 AND metadata<>'';
            CREATE TABLE IF NOT EXISTS tags(name TEXT PRIMARY KEY COLLATE NOCASE);
            CREATE TABLE IF NOT EXISTS asset_tags(asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
              tag TEXT NOT NULL REFERENCES tags(name), PRIMARY KEY(asset_id,tag));
            CREATE TABLE IF NOT EXISTS asset_prompt_terms(asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
              term TEXT NOT NULL COLLATE NOCASE, source TEXT NOT NULL,
              PRIMARY KEY(asset_id,term,source));
            CREATE INDEX IF NOT EXISTS asset_prompt_terms_term ON asset_prompt_terms(term,source,asset_id);
            CREATE TABLE IF NOT EXISTS asset_prompt_index_state(asset_id TEXT PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
              modified_utc INTEGER NOT NULL, metadata_length INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS collections(id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS collection_items(collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
              asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE, PRIMARY KEY(collection_id,asset_id));
            CREATE TABLE IF NOT EXISTS saved_queries(id TEXT PRIMARY KEY, name TEXT NOT NULL, query_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS file_operations(
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, asset_id TEXT NOT NULL,
              source_root TEXT NOT NULL, destination_root TEXT NOT NULL,
              source_relative TEXT NOT NULL, destination_relative TEXT NOT NULL,
              state TEXT NOT NULL, created_utc INTEGER NOT NULL, error TEXT NOT NULL DEFAULT '',
              size INTEGER NOT NULL DEFAULT 0, modified_utc INTEGER NOT NULL DEFAULT 0);
            """;
        command.ExecuteNonQuery();
        EnsureDimensionColumns(connection);
        EnsureOperationColumns(connection);
    }

    private static void EnsureOperationColumns(SqliteConnection connection)
    {
        var found = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        using (var check = connection.CreateCommand())
        {
            check.CommandText = "PRAGMA table_info(file_operations)";
            using var reader = check.ExecuteReader();
            while (reader.Read()) found.Add(reader.GetString(1));
        }
        foreach (var column in new[] { "size", "modified_utc" })
        {
            if (found.Contains(column)) continue;
            using var alter = connection.CreateCommand();
            alter.CommandText = $"ALTER TABLE file_operations ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0";
            alter.ExecuteNonQuery();
        }
    }

    private static void EnsureDimensionColumns(SqliteConnection connection)
    {
        var found = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        using (var check = connection.CreateCommand())
        {
            check.CommandText = "PRAGMA table_info(assets)";
            using var reader = check.ExecuteReader();
            while (reader.Read()) found.Add(reader.GetString(1));
        }
        foreach (var column in new[] { "width", "height" })
        {
            if (found.Contains(column)) continue;
            using var alter = connection.CreateCommand();
            alter.CommandText = $"ALTER TABLE assets ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0";
            alter.ExecuteNonQuery();
        }
        using var version = connection.CreateCommand();
        version.CommandText = "PRAGMA user_version=3";
        version.ExecuteNonQuery();
    }

    private SqliteConnection Open()
    {
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = database, Mode = SqliteOpenMode.ReadWriteCreate, Pooling = true
        }.ToString());
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = "PRAGMA foreign_keys=ON";
        command.ExecuteNonQuery();
        return connection;
    }

    private static void Parameter(SqliteCommand command, string name, object value) =>
        command.Parameters.AddWithValue(name, value ?? DBNull.Value);

    public List<AssetRoot> Roots()
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "SELECT id,path FROM roots ORDER BY path COLLATE NOCASE";
            using var reader = command.ExecuteReader();
            var result = new List<AssetRoot>();
            while (reader.Read()) result.Add(new AssetRoot { Id = reader.GetString(0), Path = reader.GetString(1), Online = Directory.Exists(reader.GetString(1)) });
            return result;
        }
    }

    public AssetRoot AddRoot(string path)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "INSERT OR IGNORE INTO roots(id,path) VALUES(@id,@path); SELECT id FROM roots WHERE path=@path";
            Parameter(command, "@id", Guid.NewGuid().ToString("N"));
            Parameter(command, "@path", path);
            var id = (string)command.ExecuteScalar();
            return new AssetRoot { Id = id, Path = path, Online = true };
        }
    }

    public AssetRoot Root(string id)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "SELECT path FROM roots WHERE id=@id";
            Parameter(command, "@id", id);
            var path = command.ExecuteScalar() as string;
            return path == null ? null : new AssetRoot { Id = id, Path = path, Online = Directory.Exists(path) };
        }
    }

    public List<string> RelativePaths(string rootId)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "SELECT relative_path FROM assets WHERE root_id=@root";
            Parameter(command, "@root", rootId);
            using var reader = command.ExecuteReader();
            var paths = new List<string>();
            while (reader.Read()) paths.Add(reader.GetString(0));
            return paths;
        }
    }

    public void RelinkRoot(string id, string path)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "UPDATE roots SET path=@path WHERE id=@id";
            Parameter(command, "@path", path);
            Parameter(command, "@id", id);
            if (command.ExecuteNonQuery() != 1) throw new ArgumentException("Pasta desconhecida.");
        }
    }

    public void Upsert(AssetItem item, string scanId)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = """
                INSERT INTO assets(id,root_id,relative_path,parent_path,name,is_directory,is_image,available,size,modified_utc,scan_id,metadata,width,height)
                VALUES(@id,@root,@rel,@parent,@name,@dir,@image,1,@size,@modified,@scan,@metadata,@width,@height)
                ON CONFLICT(root_id,relative_path) DO UPDATE SET
                name=excluded.name,parent_path=excluded.parent_path,is_directory=excluded.is_directory,
                is_image=excluded.is_image,available=1,size=excluded.size,modified_utc=excluded.modified_utc,
                scan_id=excluded.scan_id,width=excluded.width,height=excluded.height,
                metadata=CASE WHEN assets.modified_utc<>excluded.modified_utc OR assets.size<>excluded.size
                  THEN excluded.metadata ELSE assets.metadata END;
                """;
            Parameter(command, "@id", item.Id);
            Parameter(command, "@root", item.RootId);
            Parameter(command, "@rel", item.RelativePath);
            Parameter(command, "@parent", Parent(item.RelativePath));
            Parameter(command, "@name", item.Name);
            Parameter(command, "@dir", item.IsDirectory ? 1 : 0);
            Parameter(command, "@image", item.IsImage ? 1 : 0);
            Parameter(command, "@size", item.Size);
            Parameter(command, "@modified", item.ModifiedUtc);
            Parameter(command, "@metadata", item.Metadata);
            Parameter(command, "@width", item.Width);
            Parameter(command, "@height", item.Height);
            Parameter(command, "@scan", scanId);
            command.ExecuteNonQuery();
        }
    }

    public AssetItem ScanHint(string rootId, string relative)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "SELECT id,size,modified_utc,width,height FROM assets WHERE root_id=@root AND relative_path=@relative";
            Parameter(command, "@root", rootId);
            Parameter(command, "@relative", relative);
            using var reader = command.ExecuteReader();
            return reader.Read() ? new AssetItem { Id = reader.GetString(0), Size = reader.GetInt64(1),
                ModifiedUtc = reader.GetInt64(2), Width = reader.GetInt32(3), Height = reader.GetInt32(4) } : null;
        }
    }

    public void FinishScan(string rootId, string scanId)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "UPDATE assets SET available=0 WHERE root_id=@root AND scan_id<>@scan";
            Parameter(command, "@root", rootId);
            Parameter(command, "@scan", scanId);
            command.ExecuteNonQuery();
        }
    }

    public static string Parent(string relative)
    {
        var index = relative.LastIndexOf('/');
        return index < 0 ? "" : relative[..index];
    }

    private static AssetItem ReadAsset(SqliteDataReader reader) => new()
    {
        Id = reader.GetString(0), RootId = reader.GetString(1), RelativePath = reader.GetString(2),
        Name = reader.GetString(3), IsDirectory = reader.GetInt32(4) != 0,
        IsImage = reader.GetInt32(5) != 0, Available = reader.GetInt32(6) != 0,
        Size = reader.GetInt64(7), ModifiedUtc = reader.GetInt64(8),
        Favorite = reader.GetInt32(9) != 0, Notes = reader.GetString(10), Metadata = reader.GetString(11),
        Width = reader.GetInt32(12), Height = reader.GetInt32(13), HasMetadata = reader.GetInt32(14) != 0
    };

    private const string AssetColumns = "id,root_id,relative_path,name,is_directory,is_image,available,size,modified_utc,favorite,notes,metadata,width,height,CASE WHEN metadata<>'' THEN 1 ELSE 0 END";
    private const string AssetListColumns = "id,root_id,relative_path,name,is_directory,is_image,available,size,modified_utc,favorite,notes,'' AS metadata,width,height,CASE WHEN a.metadata<>'' THEN 1 ELSE 0 END";

    public AssetItem Asset(string id)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = $"SELECT {AssetColumns} FROM assets WHERE id=@id";
            Parameter(command, "@id", id);
            using var reader = command.ExecuteReader();
            if (!reader.Read()) return null;
            var item = ReadAsset(reader);
            reader.Close();
            item.Tags = Tags(connection, id);
            return item;
        }
    }

    private static List<string> Tags(SqliteConnection connection, string id)
    {
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT tag FROM asset_tags WHERE asset_id=@id ORDER BY tag COLLATE NOCASE";
        Parameter(command, "@id", id);
        using var reader = command.ExecuteReader();
        var tags = new List<string>();
        while (reader.Read()) tags.Add(reader.GetString(0));
        return tags;
    }

    public AssetPage Query(AssetQuery query)
    {
        if (!string.IsNullOrWhiteSpace(query.Term) && query.TermSource != "manual") RefreshPromptTerms();
        lock (gate)
        {
            using var connection = Open();
            var where = " WHERE a.available=1";
            if (!string.IsNullOrEmpty(query.RootId)) where += " AND a.root_id=@root";
            if (!string.IsNullOrEmpty(query.Folder))
                where += query.IncludeDescendants ? " AND (a.parent_path=@folder OR substr(a.parent_path,1,length(@prefix))=@prefix)" : " AND a.parent_path=@folder";
            else if (!query.IncludeDescendants && !string.IsNullOrEmpty(query.RootId)) where += " AND a.parent_path=''";
            if (query.ImagesOnly) where += " AND a.is_image=1 AND a.is_directory=0";
            if (query.MetadataOnly) where += " AND a.is_image=1 AND a.metadata<>''";
            if (query.DirectoriesOnly) where += " AND a.is_directory=1";
            if (query.FavoritesOnly) where += " AND a.favorite=1";
            if (!string.IsNullOrWhiteSpace(query.Search)) where += " AND (instr(lower(a.name),lower(@search))>0 OR instr(lower(a.notes),lower(@search))>0 OR instr(lower(a.metadata),lower(@search))>0)";
            if (!string.IsNullOrEmpty(query.Tag)) where += " AND EXISTS(SELECT 1 FROM asset_tags t WHERE t.asset_id=a.id AND t.tag=@tag)";
            if (!string.IsNullOrEmpty(query.Term)) where += query.TermSource switch
            {
                "manual" => " AND EXISTS(SELECT 1 FROM asset_tags t WHERE t.asset_id=a.id AND t.tag=@term COLLATE NOCASE)",
                "positive" or "negative" => " AND EXISTS(SELECT 1 FROM asset_prompt_terms p WHERE p.asset_id=a.id AND p.term=@term COLLATE NOCASE AND p.source=@termSource)",
                _ => " AND (EXISTS(SELECT 1 FROM asset_tags t WHERE t.asset_id=a.id AND t.tag=@term COLLATE NOCASE) OR EXISTS(SELECT 1 FROM asset_prompt_terms p WHERE p.asset_id=a.id AND p.term=@term COLLATE NOCASE))"
            };
            if (!string.IsNullOrEmpty(query.CollectionId)) where += " AND EXISTS(SELECT 1 FROM collection_items c WHERE c.asset_id=a.id AND c.collection_id=@collection)";
            if (query.MinWidth > 0) where += " AND a.width>=@minWidth";
            if (query.MinHeight > 0) where += " AND a.height>=@minHeight";
            if (query.MaxWidth > 0) where += " AND a.width<=@maxWidth";
            if (query.MaxHeight > 0) where += " AND a.height<=@maxHeight";
            using var command = connection.CreateCommand();
            if (query.Rule != null) where += " AND " + RuleSql(query.Rule, command, 0, new int[1]);
            void Bind()
            {
                Parameter(command, "@root", query.RootId);
                Parameter(command, "@folder", query.Folder);
                Parameter(command, "@prefix", query.Folder + "/");
                Parameter(command, "@search", query.Search?.Trim() ?? "");
                Parameter(command, "@tag", query.Tag);
                Parameter(command, "@term", query.Term);
                Parameter(command, "@termSource", query.TermSource);
                Parameter(command, "@collection", query.CollectionId);
                Parameter(command, "@minWidth", query.MinWidth);
                Parameter(command, "@minHeight", query.MinHeight);
                Parameter(command, "@maxWidth", query.MaxWidth);
                Parameter(command, "@maxHeight", query.MaxHeight);
            }
            command.CommandText = "SELECT count(*) FROM assets a" + where;
            Bind();
            var total = Convert.ToInt32(command.ExecuteScalar());
            var order = query.Sort switch
            {
                "date" => "a.modified_utc DESC,a.id",
                "size" => "a.size DESC,a.id",
                "type" => "a.is_directory DESC,a.is_image DESC,a.name COLLATE NOCASE,a.id",
                _ => "a.is_directory DESC,a.name COLLATE NOCASE,a.id"
            };
            command.CommandText = $"SELECT {AssetListColumns} FROM assets a{where} ORDER BY {order} LIMIT @limit OFFSET @offset";
            Parameter(command, "@limit", Math.Clamp(query.Limit, 1, 200));
            Parameter(command, "@offset", Math.Max(0, query.Offset));
            using var reader = command.ExecuteReader();
            var page = new AssetPage { Total = total };
            while (reader.Read()) page.Items.Add(ReadAsset(reader));
            reader.Close();
            foreach (var item in page.Items) item.Tags = Tags(connection, item.Id);
            page.NextOffset = Math.Max(0, query.Offset) + page.Items.Count;
            return page;
        }
    }

    private static string RuleSql(AssetRule rule, SqliteCommand command, int depth, int[] count)
    {
        if (rule == null || depth > 4 || ++count[0] > 32) throw new ArgumentException("Filtro avançado muito complexo.");
        if (rule.Mode is "all" or "any")
        {
            if (rule.Children == null || rule.Children.Count is < 1 or > 12) throw new ArgumentException("Grupo de filtros inválido.");
            return "(" + string.Join(rule.Mode == "all" ? " AND " : " OR ",
                rule.Children.Select(child => RuleSql(child, command, depth + 1, count))) + ")";
        }
        if (rule.Mode == "not")
        {
            if (rule.Children?.Count != 1) throw new ArgumentException("Negação inválida.");
            return "(NOT " + RuleSql(rule.Children[0], command, depth + 1, count) + ")";
        }
        if (rule.Mode != "predicate" || rule.Value == null || rule.Value.Length > 200)
            throw new ArgumentException("Filtro inválido.");
        var name = "@rule" + count[0];
        if (rule.Field == "tag" && rule.Comparison == "eq")
        {
            Parameter(command, name, rule.Value);
            return $"EXISTS(SELECT 1 FROM asset_tags rt WHERE rt.asset_id=a.id AND rt.tag={name})";
        }
        if (rule.Field == "favorite" && rule.Comparison == "eq")
        {
            Parameter(command, name, rule.Value == "true" ? 1 : 0);
            return $"a.favorite={name}";
        }
        var textField = rule.Field switch
        {
            "name" => "a.name", "notes" => "a.notes", "metadata" => "a.metadata", _ => ""
        };
        if (textField != "" && rule.Comparison == "contains")
        {
            Parameter(command, name, rule.Value);
            return $"instr(lower({textField}),lower({name}))>0";
        }
        var numberField = rule.Field switch
        {
            "width" => "a.width", "height" => "a.height", "size" => "a.size", "modifiedUtc" => "a.modified_utc",
            "ratio" => "(a.width * 1.0 / nullif(a.height,0))", _ => ""
        };
        var operation = rule.Comparison switch { "eq" => "=", "gte" => ">=", "lte" => "<=", _ => "" };
        if (numberField == "" || operation == "" || !double.TryParse(rule.Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var number) ||
            !double.IsFinite(number)) throw new ArgumentException("Comparação numérica inválida.");
        Parameter(command, name, number);
        return $"{numberField}{operation}{name}";
    }

    public List<string> AllTags()
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "SELECT name FROM tags ORDER BY name COLLATE NOCASE";
            using var reader = command.ExecuteReader();
            var result = new List<string>();
            while (reader.Read()) result.Add(reader.GetString(0));
            return result;
        }
    }

    private void RefreshPromptTerms()
    {
        while (true)
        {
            lock (gate)
            {
                using var connection = Open();
                using var pending = connection.CreateCommand();
                pending.CommandText = """
                    SELECT a.id,a.metadata,a.modified_utc FROM assets a
                    LEFT JOIN asset_prompt_index_state s ON s.asset_id=a.id
                    WHERE a.is_image=1 AND (s.asset_id IS NULL OR s.modified_utc<>a.modified_utc
                      OR s.metadata_length<>length(a.metadata)) LIMIT 24
                    """;
                var batch = new List<(string Id, string Metadata, long Modified)>();
                using (var reader = pending.ExecuteReader())
                    while (reader.Read()) batch.Add((reader.GetString(0), reader.GetString(1), reader.GetInt64(2)));
                if (batch.Count == 0) return;
                using var transaction = connection.BeginTransaction();
                foreach (var item in batch)
                {
                    using var remove = connection.CreateCommand();
                    remove.Transaction = transaction;
                    remove.CommandText = "DELETE FROM asset_prompt_terms WHERE asset_id=@id";
                    Parameter(remove, "@id", item.Id);
                    remove.ExecuteNonQuery();
                    foreach (var term in PromptTermExtractor.Extract(item.Metadata))
                    {
                        using var add = connection.CreateCommand();
                        add.Transaction = transaction;
                        add.CommandText = "INSERT OR IGNORE INTO asset_prompt_terms(asset_id,term,source) VALUES(@id,@term,@source)";
                        Parameter(add, "@id", item.Id);
                        Parameter(add, "@term", term.Text);
                        Parameter(add, "@source", term.Source);
                        add.ExecuteNonQuery();
                    }
                    using var state = connection.CreateCommand();
                    state.Transaction = transaction;
                    state.CommandText = """
                        INSERT INTO asset_prompt_index_state(asset_id,modified_utc,metadata_length)
                        VALUES(@id,@modified,@length) ON CONFLICT(asset_id) DO UPDATE SET
                        modified_utc=excluded.modified_utc,metadata_length=excluded.metadata_length
                        """;
                    Parameter(state, "@id", item.Id);
                    Parameter(state, "@modified", item.Modified);
                    Parameter(state, "@length", item.Metadata.Length);
                    state.ExecuteNonQuery();
                }
                transaction.Commit();
            }
        }
    }

    public AssetTagOverviewPage TagOverview(AssetTagOverviewQuery query)
    {
        RefreshPromptTerms();
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            const string counts = """
                WITH source_rows AS (
                  SELECT t.tag AS term,COUNT(*) AS manual,0 AS positive,0 AS negative
                  FROM asset_tags t JOIN assets a ON a.id=t.asset_id WHERE a.is_image=1
                  GROUP BY t.tag
                  UNION ALL
                  SELECT p.term,0,SUM(CASE WHEN p.source='positive' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN p.source='negative' THEN 1 ELSE 0 END)
                  FROM asset_prompt_terms p JOIN assets a ON a.id=p.asset_id WHERE a.is_image=1
                  GROUP BY p.term COLLATE NOCASE
                ), terms AS (
                  SELECT term,SUM(manual) AS manual,SUM(positive) AS positive,SUM(negative) AS negative
                  FROM source_rows GROUP BY term COLLATE NOCASE
                )
                """;
            const string filter = """
                WHERE instr(lower(term),lower(@search))>0 AND
                  (@source='all' OR (@source='manual' AND manual>0) OR
                   (@source='positive' AND positive>0) OR (@source='negative' AND negative>0))
                """;
            Parameter(command, "@search", query.Search?.Trim() ?? "");
            Parameter(command, "@source", query.Source);
            command.CommandText = counts + " SELECT COUNT(*) FROM terms " + filter;
            var page = new AssetTagOverviewPage { Total = Convert.ToInt32(command.ExecuteScalar()) };
            command.CommandText = counts + " SELECT term,manual,positive,negative FROM terms " + filter +
                " ORDER BY manual+positive+negative DESC,term COLLATE NOCASE LIMIT @limit OFFSET @offset";
            Parameter(command, "@limit", query.Limit);
            Parameter(command, "@offset", query.Offset);
            using var reader = command.ExecuteReader();
            while (reader.Read()) page.Items.Add(new AssetTagOverviewItem
            {
                Term = reader.GetString(0), Manual = reader.GetInt32(1), Positive = reader.GetInt32(2), Negative = reader.GetInt32(3)
            });
            page.NextOffset = query.Offset + page.Items.Count;
            return page;
        }
    }

    public List<SavedAssetQuery> SavedQueries()
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "SELECT id,name,query_json FROM saved_queries ORDER BY name COLLATE NOCASE";
            using var reader = command.ExecuteReader();
            var result = new List<SavedAssetQuery>();
            while (reader.Read()) result.Add(new SavedAssetQuery
            {
                Id = reader.GetString(0), Name = reader.GetString(1),
                Query = System.Text.Json.JsonSerializer.Deserialize<AssetQuery>(reader.GetString(2)) ?? new()
            });
            return result;
        }
    }

    public SavedAssetQuery SaveQuery(string name, AssetQuery query)
    {
        lock (gate)
        {
            var saved = new SavedAssetQuery { Id = Guid.NewGuid().ToString("N"), Name = name, Query = query };
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "INSERT INTO saved_queries(id,name,query_json) VALUES(@id,@name,@query)";
            Parameter(command, "@id", saved.Id);
            Parameter(command, "@name", saved.Name);
            Parameter(command, "@query", System.Text.Json.JsonSerializer.Serialize(query));
            command.ExecuteNonQuery();
            return saved;
        }
    }

    public void Edit(string id, bool? favorite, string notes, string addTag, string removeTag)
    {
        lock (gate)
        {
            using var connection = Open();
            using var transaction = connection.BeginTransaction();
            if (favorite != null || notes != null)
            {
                using var command = connection.CreateCommand();
                command.Transaction = transaction;
                command.CommandText = "UPDATE assets SET favorite=coalesce(@favorite,favorite),notes=coalesce(@notes,notes) WHERE id=@id";
                Parameter(command, "@id", id);
                Parameter(command, "@favorite", favorite.HasValue ? (favorite.Value ? 1 : 0) : DBNull.Value);
                Parameter(command, "@notes", notes);
                if (command.ExecuteNonQuery() != 1) throw new ArgumentException("Arquivo desconhecido.");
            }
            if (!string.IsNullOrEmpty(addTag))
            {
                using var command = connection.CreateCommand();
                command.Transaction = transaction;
                command.CommandText = "INSERT OR IGNORE INTO tags(name) VALUES(@tag); INSERT OR IGNORE INTO asset_tags(asset_id,tag) VALUES(@id,@tag)";
                Parameter(command, "@id", id);
                Parameter(command, "@tag", addTag);
                command.ExecuteNonQuery();
            }
            if (!string.IsNullOrEmpty(removeTag))
            {
                using var command = connection.CreateCommand();
                command.Transaction = transaction;
                command.CommandText = "DELETE FROM asset_tags WHERE asset_id=@id AND tag=@tag";
                Parameter(command, "@id", id);
                Parameter(command, "@tag", removeTag);
                command.ExecuteNonQuery();
            }
            transaction.Commit();
        }
    }

    public void EditBatch(AssetBatchEdit edit)
    {
        lock (gate)
        {
            using var connection = Open();
            using var transaction = connection.BeginTransaction();
            if (edit.CollectionPresent.HasValue)
            {
                using var collection = connection.CreateCommand();
                collection.Transaction = transaction;
                collection.CommandText = "SELECT 1 FROM collections WHERE id=@id";
                Parameter(collection, "@id", edit.CollectionId);
                if (collection.ExecuteScalar() == null) throw new ArgumentException("Coleção desconhecida.");
            }
            foreach (var id in edit.Ids.Distinct())
            {
                using var existing = connection.CreateCommand();
                existing.Transaction = transaction;
                existing.CommandText = "SELECT 1 FROM assets WHERE id=@id";
                Parameter(existing, "@id", id);
                if (existing.ExecuteScalar() == null) throw new ArgumentException("Item desconhecido.");
                if (edit.Favorite.HasValue)
                {
                    using var favorite = connection.CreateCommand();
                    favorite.Transaction = transaction;
                    favorite.CommandText = "UPDATE assets SET favorite=@value WHERE id=@id";
                    Parameter(favorite, "@value", edit.Favorite.Value ? 1 : 0);
                    Parameter(favorite, "@id", id);
                    if (favorite.ExecuteNonQuery() != 1) throw new ArgumentException("Item desconhecido.");
                }
                if (!string.IsNullOrEmpty(edit.AddTag))
                {
                    using var tag = connection.CreateCommand();
                    tag.Transaction = transaction;
                    tag.CommandText = "INSERT OR IGNORE INTO tags(name) VALUES(@tag); INSERT OR IGNORE INTO asset_tags(asset_id,tag) VALUES(@id,@tag)";
                    Parameter(tag, "@tag", edit.AddTag);
                    Parameter(tag, "@id", id);
                    tag.ExecuteNonQuery();
                }
                if (!string.IsNullOrEmpty(edit.RemoveTag))
                {
                    using var tag = connection.CreateCommand();
                    tag.Transaction = transaction;
                    tag.CommandText = "DELETE FROM asset_tags WHERE asset_id=@id AND tag=@tag";
                    Parameter(tag, "@tag", edit.RemoveTag);
                    Parameter(tag, "@id", id);
                    tag.ExecuteNonQuery();
                }
                if (edit.CollectionPresent.HasValue)
                {
                    using var collectionItem = connection.CreateCommand();
                    collectionItem.Transaction = transaction;
                    collectionItem.CommandText = edit.CollectionPresent.Value
                        ? "INSERT OR IGNORE INTO collection_items(collection_id,asset_id) VALUES(@collection,@asset)"
                        : "DELETE FROM collection_items WHERE collection_id=@collection AND asset_id=@asset";
                    Parameter(collectionItem, "@collection", edit.CollectionId);
                    Parameter(collectionItem, "@asset", id);
                    collectionItem.ExecuteNonQuery();
                }
            }
            transaction.Commit();
        }
    }

    public AssetCollection AddCollection(string name)
    {
        lock (gate)
        {
            var collection = new AssetCollection { Id = Guid.NewGuid().ToString("N"), Name = name };
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "INSERT INTO collections(id,name) VALUES(@id,@name)";
            Parameter(command, "@id", collection.Id);
            Parameter(command, "@name", name);
            command.ExecuteNonQuery();
            return collection;
        }
    }

    public List<AssetCollection> Collections()
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "SELECT id,name FROM collections ORDER BY name COLLATE NOCASE";
            using var reader = command.ExecuteReader();
            var result = new List<AssetCollection>();
            while (reader.Read()) result.Add(new AssetCollection { Id = reader.GetString(0), Name = reader.GetString(1) });
            return result;
        }
    }

    public void SetCollectionItem(string collectionId, string assetId, bool present)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = present
                ? "INSERT OR IGNORE INTO collection_items(collection_id,asset_id) VALUES(@collection,@asset)"
                : "DELETE FROM collection_items WHERE collection_id=@collection AND asset_id=@asset";
            Parameter(command, "@collection", collectionId);
            Parameter(command, "@asset", assetId);
            command.ExecuteNonQuery();
        }
    }

    public void Backup(string destination)
    {
        var full = Path.GetFullPath(destination);
        if (string.Equals(full, Path.GetFullPath(database), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Escolha outro arquivo para o backup.");
        lock (gate)
        {
            using var source = Open();
            using var target = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = full, Pooling = false }.ToString());
            target.Open();
            source.BackupDatabase(target);
        }
    }

    public void BeginFileOperation(string id, string kind, AssetFilePlanItem item)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = """
                INSERT INTO file_operations(id,kind,asset_id,source_root,destination_root,source_relative,destination_relative,state,created_utc,size,modified_utc)
                VALUES(@id,@kind,@asset,@sourceRoot,@destinationRoot,@source,@destination,'running',@created,@size,@modified)
                """;
            Parameter(command, "@id", id);
            Parameter(command, "@kind", kind);
            Parameter(command, "@asset", item.AssetId);
            Parameter(command, "@sourceRoot", item.SourceRootId);
            Parameter(command, "@destinationRoot", item.DestinationRootId);
            Parameter(command, "@source", item.SourceRelativePath);
            Parameter(command, "@destination", item.DestinationRelativePath);
            Parameter(command, "@created", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
            Parameter(command, "@size", item.Size);
            Parameter(command, "@modified", item.ModifiedUtc);
            command.ExecuteNonQuery();
        }
    }

    public List<AssetOperation> RecentOperations(int limit = 30)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "SELECT id,kind,asset_id,source_root,destination_root,source_relative,destination_relative,state,error,created_utc,size,modified_utc FROM file_operations ORDER BY created_utc DESC LIMIT @limit";
            Parameter(command, "@limit", Math.Clamp(limit, 1, 10000));
            using var reader = command.ExecuteReader();
            var result = new List<AssetOperation>();
            while (reader.Read()) result.Add(new AssetOperation
            {
                Id = reader.GetString(0), Kind = reader.GetString(1), AssetId = reader.GetString(2),
                SourceRootId = reader.GetString(3), DestinationRootId = reader.GetString(4),
                SourceRelativePath = reader.GetString(5), DestinationRelativePath = reader.GetString(6),
                State = reader.GetString(7), Error = reader.GetString(8), CreatedUtc = reader.GetInt64(9),
                Size = reader.GetInt64(10), ModifiedUtc = reader.GetInt64(11)
            });
            return result;
        }
    }

    public void FinishFileOperation(string id, string state, string error = "")
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "UPDATE file_operations SET state=@state,error=@error WHERE id=@id";
            Parameter(command, "@id", id);
            Parameter(command, "@state", state);
            Parameter(command, "@error", error);
            command.ExecuteNonQuery();
        }
    }

    public void MoveRecords(AssetFilePlanItem item)
    {
        lock (gate)
        {
            using var connection = Open();
            using var transaction = connection.BeginTransaction();
            using var command = connection.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = """
                UPDATE assets SET root_id=@destinationRoot,
                  relative_path=@destination || substr(relative_path,length(@source)+1),
                  parent_path=CASE WHEN parent_path=@source THEN @destination
                    WHEN substr(parent_path,1,length(@source)+1)=@source||'/' THEN @destination||substr(parent_path,length(@source)+1)
                    ELSE @destinationParent END,
                  name=CASE WHEN id=@id THEN @name ELSE name END
                WHERE root_id=@sourceRoot AND (id=@id OR (is_directory=0 OR is_directory=1)
                  AND substr(relative_path,1,length(@source)+1)=@source||'/');
                """;
            Parameter(command, "@id", item.AssetId);
            Parameter(command, "@sourceRoot", item.SourceRootId);
            Parameter(command, "@destinationRoot", item.DestinationRootId);
            Parameter(command, "@source", item.SourceRelativePath);
            Parameter(command, "@destination", item.DestinationRelativePath);
            Parameter(command, "@destinationParent", Parent(item.DestinationRelativePath));
            Parameter(command, "@name", Path.GetFileName(item.DestinationRelativePath));
            command.ExecuteNonQuery();
            transaction.Commit();
        }
    }

    public void MarkUnavailable(AssetFilePlanItem item)
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "UPDATE assets SET available=0 WHERE root_id=@root AND (id=@id OR substr(relative_path,1,length(@source)+1)=@source||'/')";
            Parameter(command, "@root", item.SourceRootId);
            Parameter(command, "@id", item.AssetId);
            Parameter(command, "@source", item.SourceRelativePath);
            command.ExecuteNonQuery();
        }
    }

    public void MarkInterruptedOperations()
    {
        lock (gate)
        {
            using var connection = Open();
            using var command = connection.CreateCommand();
            command.CommandText = "UPDATE file_operations SET state='interrupted',error='Verifique origem e destino antes de repetir.' WHERE state='running'";
            command.ExecuteNonQuery();
        }
    }
}
