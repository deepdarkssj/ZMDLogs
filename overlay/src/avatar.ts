import actorImageTable from '../../jsondata/ActorImageTable.json';

type ActorImageEntry = {
  avatarPath?: string;
};

const IMAGE_TABLE = actorImageTable as Record<string, ActorImageEntry>;

const normalizePath = (path: string): string => path.replace(/\\/g, '/');

const getAssetRoot = (): string => {
  const params = new URLSearchParams(window.location.search);
  return params.get('assetRoot') ?? __REPO_ROOT__;
};

const toRuntimeUrl = (absolutePath: string): string => {
  const normalized = normalizePath(absolutePath);
  if (window.location.protocol === 'file:') {
    return encodeURI(`file:///${normalized}`);
  }
  return encodeURI(`${window.location.origin}/@fs/${normalized}`);
};

export const getAvatarUrl = (templateId: string | null): string | null => {
  if (!templateId) {
    return null;
  }
  const avatarPath = IMAGE_TABLE[templateId]?.avatarPath;
  if (!avatarPath) {
    return null;
  }
  const absolutePath = `${getAssetRoot()}/icon/Texture2D/${avatarPath}.png`;
  return toRuntimeUrl(absolutePath);
};
