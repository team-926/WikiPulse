package io.wikipulse.backend.matching;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * {@link ClusterEmbeddingSource} 실제 구현: Wikipedia 도입부 → 대표 텍스트(§6.2) → GMS 임베딩.
 */
@Component
public class WikipediaGmsEmbeddingSource implements ClusterEmbeddingSource {

    private final WikipediaExtractClient wikipedia;
    private final GmsEmbeddingClient embeddingClient;
    private final CandidateProperties props;

    public WikipediaGmsEmbeddingSource(
            WikipediaExtractClient wikipedia,
            GmsEmbeddingClient embeddingClient,
            CandidateProperties props) {
        this.wikipedia = wikipedia;
        this.embeddingClient = embeddingClient;
        this.props = props;
    }

    @Override
    public Optional<float[]> embed(List<String> orderedTitles) {
        if (orderedTitles == null || orderedTitles.isEmpty()) {
            return Optional.empty();
        }
        List<IssueRepresentativeText.Member> members = new ArrayList<>(orderedTitles.size());
        for (String title : orderedTitles) {
            members.add(new IssueRepresentativeText.Member(title, wikipedia.intro(title)));
        }
        String text = IssueRepresentativeText.build(members, props.getMaxChars());
        if (text.isBlank()) {
            return Optional.empty();
        }
        return Optional.of(embeddingClient.embed(text));
    }
}
