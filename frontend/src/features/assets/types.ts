export interface AssetRoot { id: string; path: string; online: boolean }
export interface AssetRelinkPlan { id: string; rootId: string; oldPath: string; newPath: string; matched: number; missing: number; expiresUtc: number }
export interface AssetItem {
  id: string; rootId: string; relativePath: string; name: string;
  isDirectory: boolean; isImage: boolean; available: boolean;
  size: number; modifiedUtc: number; width: number; height: number; favorite: boolean; notes: string;
  metadata: string; hasMetadata: boolean; tags: string[];
}
export interface AssetPage { items: AssetItem[]; total: number; nextOffset: number }
export interface AssetCollection { id: string; name: string }
export interface AssetNamingRule { baseName: string; pattern: string; scope: 'all' | 'conflicts'; autoContinue: boolean; startNumber: number; digits: number }
export interface AssetFileChoice { assetId: string; action: 'rename' | 'skip'; name: string }
export interface AssetTagOverviewItem { term: string; manual: number; positive: number; negative: number }
export interface AssetTagOverviewPage { items: AssetTagOverviewItem[]; total: number; nextOffset: number }
export interface AssetRule { mode: 'all' | 'any' | 'not' | 'predicate'; field?: string; comparison?: string; value?: string; children?: AssetRule[] }
export interface SavedAssetQuery { id: string; name: string; query: AssetQuery }
export interface AssetJob { id: string; rootId: string; state: string; seen: number; error: string }
export interface AssetOperation { id: string; kind: string; sourceRelativePath: string; destinationRelativePath: string;
  state: string; error: string; createdUtc: number }
export type AssetView = 'gallery' | 'explorer';
export type AssetQuery = {
  rootId: string; folder: string; search: string; tag: string; term: string; termSource: 'all' | 'manual' | 'positive' | 'negative'; collectionId: string;
  favoritesOnly: boolean; imagesOnly: boolean; metadataOnly: boolean; directoriesOnly?: boolean; includeDescendants: boolean;
  sort: 'name' | 'date' | 'size' | 'type'; offset: number; limit: number;
  minWidth: number; minHeight: number; maxWidth: number; maxHeight: number; rule: AssetRule | null;
};
export const mediaUrl = (item: AssetItem, variant: 'thumb' | 'preview') =>
  `https://xennex-media.invalid/__asset/${item.id}/${variant}?v=${item.modifiedUtc}`;
