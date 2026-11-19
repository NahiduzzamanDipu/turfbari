import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Camera, ImagePlus, Loader2, Star, Trash2, Upload } from "lucide-react";
import type * as React from "react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { TurfArt } from "@/features/public/shared";
import { api } from "@/lib/api";
import type { TurfSettings, WorkspacePhoto } from "@/lib/types";
import { cn } from "@/lib/utils";
import { errorText } from "./hooks";

const MAX_PHOTOS = 12;
const MAX_MB = 10;
const ACCEPT = "image/jpeg,image/png,image/webp";

function tooBig(files: File[]): File | undefined {
  return files.find((f) => f.size > MAX_MB * 1024 * 1024);
}

/** Profile picture + public-page gallery, managed from Workspace → Settings. */
export function PicturesCard({ settings, canEdit }: { settings: TurfSettings; canEdit: boolean }) {
  return (
    <Card className="xl:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Camera className="size-4" /> Pictures
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-6 md:grid-cols-[14rem_1fr]">
        <ProfilePicture settings={settings} canEdit={canEdit} />
        <Gallery canEdit={canEdit} slug={settings.slug} />
      </CardContent>
    </Card>
  );
}

function ProfilePicture({ settings, canEdit }: { settings: TurfSettings; canEdit: boolean }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["ws", "settings"] });
    qc.invalidateQueries({ queryKey: ["public"] });
  };
  const upload = useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append("image", file);
      return api<{ profile_image_url: string }>("/workspace/profile-picture/", { method: "POST", body });
    },
    onSuccess: () => {
      toast.success("Profile picture updated");
      refresh();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const remove = useMutation({
    mutationFn: () => api("/workspace/profile-picture/", { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Profile picture removed");
      refresh();
    },
    onError: (e) => toast.error(errorText(e)),
  });

  return (
    <section className="flex flex-col items-center gap-3 text-center">
      <h3 className="self-start text-sm font-semibold">Profile picture</h3>
      <button
        type="button"
        disabled={!canEdit || upload.isPending}
        onClick={() => input.current?.click()}
        className="group relative size-36 overflow-hidden rounded-full border-4 border-background shadow-md ring-1 ring-border disabled:cursor-default"
        aria-label={settings.profile_image_url ? "Change profile picture" : "Upload profile picture"}
      >
        {settings.profile_image_url ? (
          <img src={settings.profile_image_url} alt="" className="size-full object-cover" />
        ) : (
          <TurfArt seed={settings.slug} className="size-full" />
        )}
        {canEdit && (
          <span className="absolute inset-0 flex items-center justify-center bg-black/45 text-white opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
            {upload.isPending ? <Loader2 className="size-6 animate-spin" /> : <Camera className="size-6" />}
          </span>
        )}
      </button>
      <p className="text-xs text-muted-foreground">Logo or entrance photo. Cropped to a square; shown on your card and page.</p>
      {canEdit && (
        <div className="flex gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => input.current?.click()} disabled={upload.isPending}>
            <Upload /> {settings.profile_image_url ? "Change" : "Upload"}
          </Button>
          {settings.profile_image_url && (
            <Button type="button" size="sm" variant="ghost" onClick={() => remove.mutate()} disabled={remove.isPending}>
              Remove
            </Button>
          )}
        </div>
      )}
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          if (tooBig([file])) toast.error(`Pictures must be ${MAX_MB} MB or smaller.`);
          else upload.mutate(file);
        }}
      />
    </section>
  );
}

function Gallery({ canEdit, slug }: { canEdit: boolean; slug: string }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const photos = useQuery({ queryKey: ["ws", "photos"], queryFn: () => api<WorkspacePhoto[]>("/workspace/photos/") });
  const list = photos.data ?? [];
  const room = MAX_PHOTOS - list.length;
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["ws", "photos"] });
    qc.invalidateQueries({ queryKey: ["public"] });
  };

  const upload = useMutation({
    mutationFn: (files: File[]) => {
      const body = new FormData();
      for (const f of files) body.append("image", f);
      return api<WorkspacePhoto[]>("/workspace/photos/", { method: "POST", body });
    },
    onSuccess: (added) => {
      toast.success(`${added.length} photo${added.length === 1 ? "" : "s"} added`);
      refresh();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/workspace/photos/${id}/`, { method: "DELETE" }),
    onSuccess: refresh,
    onError: (e) => toast.error(errorText(e)),
  });
  const caption = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string }) =>
      api(`/workspace/photos/${id}/`, { method: "PATCH", json: { caption: value } }),
    onSuccess: () => {
      toast.success("Caption saved");
      refresh();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const reorder = useMutation({
    mutationFn: (ids: string[]) => api<WorkspacePhoto[]>("/workspace/photos/reorder/", { method: "POST", json: { ids } }),
    onMutate: (ids) => {
      const byId = new Map(list.map((p) => [p.id, p]));
      qc.setQueryData(["ws", "photos"], ids.map((id) => byId.get(id)!));
    },
    onSettled: refresh,
  });

  const add = (files: File[]) => {
    const images = files.filter((f) => ACCEPT.split(",").includes(f.type));
    if (images.length < files.length) toast.error("Only JPG, PNG or WebP pictures can be added.");
    if (!images.length) return;
    if (tooBig(images)) return toast.error(`Each picture must be ${MAX_MB} MB or smaller.`);
    if (images.length > room) return toast.error(`You can add ${room} more photo${room === 1 ? "" : "s"} (limit ${MAX_PHOTOS}).`);
    upload.mutate(images);
  };

  const move = (index: number, delta: number) => {
    const ids = list.map((p) => p.id);
    const [moved] = ids.splice(index, 1);
    ids.splice(index + delta, 0, moved!);
    reorder.mutate(ids);
  };

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">
          Public page photos <span className="font-normal text-muted-foreground">· {list.length}/{MAX_PHOTOS}</span>
        </h3>
        <a href={`/turfs/${slug}`} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">
          See your public page
        </a>
      </div>
      <p className="text-xs text-muted-foreground">
        The first photo is the cover of your booking page. JPG, PNG or WebP up to {MAX_MB} MB; we resize them and remove
        camera and location data.
      </p>

      {photos.isPending && <Skeleton className="h-40" />}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {list.map((p, i) => (
          <figure key={p.id} className="group flex flex-col gap-1.5">
            <div className="relative aspect-[4/3] overflow-hidden rounded-lg border bg-muted">
              <img src={p.thumbnail_url} alt={p.caption || `Photo ${i + 1}`} loading="lazy" className="size-full object-cover" />
              {i === 0 && (
                <span className="absolute left-2 top-2 flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-[11px] font-semibold text-white">
                  <Star className="size-3" /> Cover
                </span>
              )}
              {canEdit && (
                <div className="absolute inset-x-0 bottom-0 flex justify-between bg-gradient-to-t from-black/70 to-transparent p-1.5 opacity-100 transition sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
                  <div className="flex gap-1">
                    <IconBtn label="Move earlier" disabled={i === 0 || reorder.isPending} onClick={() => move(i, -1)}>
                      <ArrowLeft />
                    </IconBtn>
                    <IconBtn label="Move later" disabled={i === list.length - 1 || reorder.isPending} onClick={() => move(i, 1)}>
                      <ArrowRight />
                    </IconBtn>
                    {i !== 0 && (
                      <IconBtn label="Make cover" disabled={reorder.isPending} onClick={() => move(i, -i)}>
                        <Star />
                      </IconBtn>
                    )}
                  </div>
                  <IconBtn
                    label="Delete photo"
                    disabled={remove.isPending}
                    onClick={() => window.confirm("Delete this photo from your public page?") && remove.mutate(p.id)}
                  >
                    <Trash2 />
                  </IconBtn>
                </div>
              )}
            </div>
            {canEdit ? (
              <Input
                aria-label={`Caption for photo ${i + 1}`}
                placeholder="Add a caption"
                defaultValue={p.caption}
                maxLength={140}
                className="h-8 text-xs"
                onBlur={(e) => {
                  const value = e.target.value.trim();
                  if (value !== p.caption) caption.mutate({ id: p.id, value });
                }}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), e.currentTarget.blur())}
              />
            ) : (
              p.caption && <figcaption className="text-xs text-muted-foreground">{p.caption}</figcaption>
            )}
          </figure>
        ))}

        {canEdit && room > 0 && (
          <button
            type="button"
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              add(Array.from(e.dataTransfer.files));
            }}
            disabled={upload.isPending}
            className={cn(
              "flex aspect-[4/3] flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed text-sm text-muted-foreground transition hover:border-primary hover:text-foreground",
              dragging && "border-primary bg-primary/5 text-foreground",
            )}
          >
            {upload.isPending ? <Loader2 className="size-6 animate-spin" /> : <ImagePlus className="size-6" />}
            {upload.isPending ? "Uploading…" : "Add photos"}
            <span className="text-[11px]">or drop them here</span>
          </button>
        )}
      </div>
      {!canEdit && list.length === 0 && <p className="text-sm text-muted-foreground">No photos yet.</p>}
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          add(files);
        }}
      />
    </section>
  );
}

function IconBtn({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="flex size-7 items-center justify-center rounded-md bg-white/90 text-neutral-900 shadow transition hover:bg-white disabled:opacity-40 [&_svg]:size-3.5"
    >
      {children}
    </button>
  );
}
