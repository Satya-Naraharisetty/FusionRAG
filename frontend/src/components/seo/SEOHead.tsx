import React, { useEffect } from "react";

export interface SEOHeadProps {
  title?: string;
  description?: string;
  keywords?: string;
  canonicalUrl?: string;
  ogImage?: string;
  robots?: string;
}

const DEFAULT_TITLE = "FusionRAG — Unified Enterprise Hybrid Retrieval & Document QA";
const DEFAULT_DESCRIPTION =
  "FusionRAG is a production-ready Hybrid RAG platform combining dense vector search, BM25 sparse retrieval, neural cross-encoder reranking, and citation-grounded generation.";
const DEFAULT_CANONICAL = "https://fusionrag.vercel.app/";
const DEFAULT_OG_IMAGE = "https://fusionrag.vercel.app/og-image.png";

export const SEOHead: React.FC<SEOHeadProps> = ({
  title,
  description = DEFAULT_DESCRIPTION,
  keywords,
  canonicalUrl = DEFAULT_CANONICAL,
  ogImage = DEFAULT_OG_IMAGE,
  robots = "index, follow",
}) => {
  useEffect(() => {
    // 1. Update Document Title
    const fullTitle = title
      ? `${title} | FusionRAG`
      : DEFAULT_TITLE;
    document.title = fullTitle;

    // Helper to safely set or create meta elements
    const setMetaTag = (attributeName: string, attributeValue: string, content: string) => {
      let tag = document.querySelector(`meta[${attributeName}="${attributeValue}"]`) as HTMLMetaElement;
      if (!tag) {
        tag = document.createElement("meta");
        tag.setAttribute(attributeName, attributeValue);
        document.head.appendChild(tag);
      }
      tag.setAttribute("content", content);
    };

    // 2. Set Standard Meta Tags
    setMetaTag("name", "description", description);
    setMetaTag("name", "robots", robots);
    if (keywords) {
      setMetaTag("name", "keywords", keywords);
    }

    // 3. Set OpenGraph Tags
    setMetaTag("property", "og:title", fullTitle);
    setMetaTag("property", "og:description", description);
    setMetaTag("property", "og:url", canonicalUrl);
    setMetaTag("property", "og:image", ogImage);

    // 4. Set Twitter Tags
    setMetaTag("name", "twitter:title", fullTitle);
    setMetaTag("name", "twitter:description", description);
    setMetaTag("name", "twitter:image", ogImage);

    // 5. Update Canonical Link
    let canonicalLink = document.querySelector('link[rel="canonical"]') as HTMLLinkElement;
    if (!canonicalLink) {
      canonicalLink = document.createElement("link");
      canonicalLink.setAttribute("rel", "canonical");
      document.head.appendChild(canonicalLink);
    }
    canonicalLink.setAttribute("href", canonicalUrl);
  }, [title, description, keywords, canonicalUrl, ogImage, robots]);

  return null;
};

export default SEOHead;
