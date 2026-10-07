import { useTranslations } from "next-intl";
import HeroSection from "@/components/layout/HeroSection";
import HowItWorks from "@/components/layout/HowItWorks";
import StatsBar from "@/components/layout/StatsBar";

export default function HomePage() {
  return (
    <>
      <HeroSection />
      <StatsBar />
      <HowItWorks />
    </>
  );
}
